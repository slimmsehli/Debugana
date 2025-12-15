`timescale 1ns/1ps

// ------------------------------------------------------------
// Import UVM
// ------------------------------------------------------------
import uvm_pkg::*;
`include "uvm_macros.svh"

// ------------------------------------------------------------
// DUT
// ------------------------------------------------------------
module dut (
    input  logic clk,
    input  logic rst_n,
    input  logic enable,
    output logic [3:0] count
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 4'd0;
        else if (enable)
            count <= count + 1;
    end

endmodule

// ------------------------------------------------------------
// Interface
// ------------------------------------------------------------
interface dut_if(input logic clk);
    logic rst_n;
    logic enable;
    logic [3:0] count;
endinterface

// ------------------------------------------------------------
// Driver
// ------------------------------------------------------------
class simple_driver extends uvm_driver #(uvm_sequence_item);
    `uvm_component_utils(simple_driver)

    virtual dut_if vif;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
        if (!uvm_config_db#(virtual dut_if)::get(this, "", "vif", vif))
            `uvm_fatal("DRV", "Virtual interface not set")
    endfunction

    task run_phase(uvm_phase phase);
        `uvm_info("DRV", "Starting stimulus", UVM_LOW)

        vif.rst_n  <= 0;
        vif.enable <= 0;
        repeat (2) @(posedge vif.clk);

        vif.rst_n <= 1;
        `uvm_info("DRV", "Reset deasserted", UVM_LOW)

        vif.enable <= 1;
        repeat (5) @(posedge vif.clk);

        `uvm_info("DRV", "Stimulus completed", UVM_LOW)
    endtask
endclass

// ------------------------------------------------------------
// Monitor
// ------------------------------------------------------------
class simple_monitor extends uvm_monitor;
    `uvm_component_utils(simple_monitor)

    virtual dut_if vif;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
        if (!uvm_config_db#(virtual dut_if)::get(this, "", "vif", vif))
            `uvm_fatal("MON", "Virtual interface not set")
    endfunction

    task run_phase(uvm_phase phase);
        forever begin
            @(posedge vif.clk);
            `uvm_info("MON",
                      $sformatf("Observed count = %0d", vif.count),
                      UVM_LOW)
        end
    endtask
endclass

// ------------------------------------------------------------
// Environment
// ------------------------------------------------------------
class simple_env extends uvm_env;
    `uvm_component_utils(simple_env)

    simple_driver  drv;
    simple_monitor mon;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
        drv = simple_driver ::type_id::create("drv", this);
        mon = simple_monitor::type_id::create("mon", this);
    endfunction
endclass

// ------------------------------------------------------------
// Test
// ------------------------------------------------------------
class simple_test extends uvm_test;
    `uvm_component_utils(simple_test)

    simple_env env;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
        env = simple_env::type_id::create("env", this);
    endfunction

    task run_phase(uvm_phase phase);
        phase.raise_objection(this);

        `uvm_info("TEST", "Test started", UVM_LOW)

        #100;

        // Intentional failure
        if (env.mon.vif.count != 4'd10) begin
            `uvm_error("TEST",
                       $sformatf("Expected count=10, got %0d",
                                 env.mon.vif.count))
        end

        `uvm_info("TEST", "Test finished", UVM_LOW)
        phase.drop_objection(this);
    endtask
endclass

// ------------------------------------------------------------
// Top-level Testbench
// ------------------------------------------------------------
module tb;

    logic clk;
    always #5 clk = ~clk;

    dut_if dut_if_inst(clk);

    dut u_dut (
        .clk    (clk),
        .rst_n  (dut_if_inst.rst_n),
        .enable (dut_if_inst.enable),
        .count  (dut_if_inst.count)
    );

    initial begin
        clk = 0;

        // VCD dump
        $dumpfile("sim.vcd");
        $dumpvars(0, tb);

        // Pass interface to UVM
        uvm_config_db#(virtual dut_if)::set(null, "*", "vif", dut_if_inst);

        run_test("simple_test");
    end

endmodule
