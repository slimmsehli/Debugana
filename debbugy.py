
# 1. Configuration
MODEL_NAME = "gpt-4.1-mini"   # example; configurable
MAX_CONTEXT_LINES = 15

# 2. UVM Log Parsing (First Error + Context)

def extract_first_uvm_error(log_path, context_lines=10):
    import re
    from collections import deque

    error_patterns = [
        re.compile(r"(UVM_ERROR|UVM_FATAL).*?([\w./\\-]+)\((\d+)\)", re.I),
        re.compile(r"\*\*\s*Error:\s*([\w./\\-]+)\((\d+)\)", re.I),
    ]

    prev = deque(maxlen=context_lines)

    with open(log_path, "r", errors="ignore") as f:
        for i, line in enumerate(f, start=1):
            prev.append(line.rstrip())

            for pat in error_patterns:
                m = pat.search(line)
                if m:
                    return {
                        "log_line": i,
                        "error_text": line.strip(),
                        "tb_file": m.group(2),
                        "tb_line": int(m.group(3)),
                        "context": list(prev)[:-1],
                    }
    return None

# 3. Related Testbench File Discovery
def find_related_tb_files(tb_file, search_paths):
    related = set()

    import os
    import re

    include_re = re.compile(r'`include\s+"([^"]+)"')

    def scan(file):
        if not os.path.exists(file):
            return
        related.add(file)
        with open(file, "r", errors="ignore") as f:
            for line in f:
                m = include_re.search(line)
                if m:
                    for p in search_paths:
                        inc = os.path.join(p, m.group(1))
                        if os.path.exists(inc):
                            scan(inc)

    scan(tb_file)
    return list(related)

# 4. LLM Interface (ChatGPT)
from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# 5. Ask the LLM What to Look for in the VCD
def ask_llm_for_debug_plan(error_info, related_files):
    prompt = f"""
You are RTL-DEBUGGER, an expert-level AI agent specialized in RTL, UVM, and hardware verification debugging.
Your purpose is to identify the root cause of a simulation errors by correlating:
Simulation logs
Waveform data (VCD)
RTL and testbench source code
You must operate strictly as an analytical engineer, not as a generic chatbot.
before giving an answer verify that the suggested signals and code already exist in the original source code and waveform 
the final answer should explain the issue and give actual fix like code changes or wave inspection 

UVM ERROR:
{error_info['error_text']}

ERROR LOCATION:
File: {error_info['tb_file']}:{error_info['tb_line']}

PREVIOUS LOG CONTEXT:
{chr(10).join(error_info['context'])}

RELATED TESTBENCH FILES:
{chr(10).join(related_files)}

Task:
1. Identify the most likely root cause category.
2. Identify relevant DUT or TB signals to inspect.
3. Specify time window(s) of interest relative to the error.
4. Output a JSON object with:
   - signals: list of signal names
   - start_time
   - end_time
   - reasoning
Give a brief and final response with the suggested fix  
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return response.choices[0].message.content

# 6. VCD Signal Extraction
def extract_vcd_window(vcd_file, signal, start, end):
    results = []
    current_time = 0

    with open(vcd_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#"):
                current_time = int(line[1:])
                continue
            if start <= current_time <= end and signal in line:
                results.append((current_time, line))

    return results

#7. Feed VCD Evidence Back to the LLM
def analyze_with_vcd(error_info, debug_plan, vcd_data):
    prompt = f"""
UVM ERROR:
{error_info['error_text']}

DEBUG PLAN:
{debug_plan}

VCD EXTRACTS:
{vcd_data}

Task:
1. Determine the root cause.
2. Identify whether the issue is TB, DUT, or interface.
3. Propose a concrete fix
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return response.choices[0].message.content

#8. Orchestrator (Main Entry Point)
import json
import re

def parse_llm_json(text):
    if not text or not text.strip():
        raise ValueError("LLM returned empty response")

    # Remove markdown fences
    text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()

    # Extract first JSON object
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM response")

    return json.loads(match.group(0))

def get_debug_plan_with_retry(error_info, related_files, retries=2):
    for attempt in range(retries + 1):
        response = ask_llm_for_debug_plan(error_info, related_files)
        try:
            return parse_llm_json(response)
        except Exception as e:
            if attempt == retries:
                raise RuntimeError(
                    f"Failed to parse LLM JSON after {retries+1} attempts"
                ) from e


def run_ai_debug(log_file, vcd_file, tb_search_paths):
    error_info = extract_first_uvm_error(log_file, MAX_CONTEXT_LINES)
    if not error_info:
        raise RuntimeError("No UVM error found")

    related = find_related_tb_files(
        error_info["tb_file"], tb_search_paths
    )

    debug_plan = ask_llm_for_debug_plan(error_info, related)

    import json
    print("LLM RAW OUTPUT:")
    print(debug_plan)
    # plan = json.loads(debug_plan) # replaced because of json output file issue
    # plan = parse_llm_json(debug_plan)
    plan = get_debug_plan_with_retry(error_info, related)

    vcd_data = {}
    for sig in plan["signals"]:
        vcd_data[sig] = extract_vcd_window(
            vcd_file,
            sig,
            plan["start_time"],
            plan["end_time"],
        )

    final_report = analyze_with_vcd(
        error_info, debug_plan, vcd_data
    )

    return final_report

## run main
report = run_ai_debug("./dv/sim.log", "./dv/sim.vcd", "./dv")
print("final report for UVM error analysis", report)


