"""Explain a given instruction in the Binary Ninja interface."""
from binaryninja import LowLevelILOperation, PluginCommand, log_info, log_error

try:
    from binja_explain_instruction.gui import explain_window
except ImportError:
    log_info("PyQt5 Gui unavailable; falling back to MessageBox hack")
    from .native_gui import explain_window

from .instruction_state import get_state
from .explain import explain_llil, fold_multi_il
from .util import get_function_at, find_mlil, find_llil, find_lifted_il, inst_in_func, dereference_symbols

import traceback

arch = None
architecture_specific_explanation_function = lambda *_: (False, ["Architecture-specific explanations unavailable"])


def init_plugin(bv):
    """ Creates the plugin window and sets up the architecture-specific functions """
    global arch, architecture_specific_explanation_function

    # Sets up architecture-specific functions
    if bv.arch.name != arch:
        if "x86" in bv.arch.name:
            from binja_explain_instruction.x86 import explain, get_doc_url
        elif "mips" in bv.arch.name:
            from binja_explain_instruction.mips import explain, get_doc_url
        elif "aarch64" in bv.arch.name:
            from binja_explain_instruction.aarch64 import explain, get_doc_url
        elif "arm" in bv.arch.name or "thumb" in bv.arch.name:  # Note: completely untested on thumb2.
            from binja_explain_instruction.ual import explain, get_doc_url
        elif "6502" in bv.arch.name:
            from binja_explain_instruction.asm6502 import explain, get_doc_url
        elif "msp430" in bv.arch.name:
            from binja_explain_instruction.msp430 import explain, get_doc_url
        elif "powerpc" in bv.arch.name:
            # PowerPC support will likely be added in Binja v1.1; may need to change the arch name
            from binja_explain_instruction.powerpc import explain, get_doc_url
        else:
            raise TypeError("Could not identify architecture type!")

        explain_window().get_doc_url = get_doc_url
        architecture_specific_explanation_function = explain.arch_explain_instruction
        arch = bv.arch.name


def explain_instruction(bv, addr):
    """ Callback for the menu item that passes the information to the GUI """
    init_plugin(bv)

    # Get the relevant information for this address
    func = get_function_at(bv, addr)
    instruction = inst_in_func(func, addr)
    lifted_il_list = find_lifted_il(func, addr)
    llil_list = find_llil(func, addr)
    mlil_list = find_mlil(func, addr)

    # Typically, we use the Low Level IL for parsing instructions. However, sometimes there isn't a corresponding
    # LLIL instruction (like for cmp), so in cases like that, we use the lifted IL, which is closer to the raw assembly
    parse_il = fold_multi_il(bv, llil_list if len(llil_list) > 0 else lifted_il_list)

    # Give the architecture submodule a chance to supply an explanation for this instruction that takes precedence
    # over the one generated via the LLIL
    should_supersede_llil, explanation_list = architecture_specific_explanation_function(
        bv, instruction, lifted_il_list
    )

    # Display the raw instruction
    try:
        explain_window().instruction = f"{hex(addr).replace('L', '')}:  {instruction}"
    except Exception:
        traceback.print_exc()

    if len(explanation_list) > 0:
        if should_supersede_llil:
            # If we got an architecture-specific explanation and it should supersede the LLIL, use that
            explain_window().description = [explanation for explanation in explanation_list]
        else:
            # Otherwise, just prepend the arch-specific explanation to the LLIL explanation
            explain_window().description = [explanation for explanation in explanation_list] + [
                explain_llil(bv, llil) for llil in parse_il
            ]
    else:
        # By default, we just use the LLIL explanation
        # We append the line number if we're displaying a conditional.
        explain_window().description = [explain_llil(bv, llil) for llil in parse_il]

    # Display the MLIL and LLIL, dereferencing anything that looks like a hex number into a symbol if possible
    explain_window().llil = [dereference_symbols(bv, llil) for llil in llil_list]
    explain_window().mlil = [dereference_symbols(bv, mlil) for mlil in mlil_list]

    # Pass in the flags, straight from the API. We don't do much with these, but they might make things more clear
    explain_window().flags = [
        (
            func.get_flags_read_by_lifted_il_instruction(lifted.instr_index),
            func.get_flags_written_by_lifted_il_instruction(lifted.instr_index),
            lifted,
        )
        for lifted in lifted_il_list
    ]

    # Display what information we can calculate about the program state before the instruction is executed
    try:
        explain_window().state = get_state(bv, addr)
    except AttributeError:
        log_error("No instruction state support for this architecture")

    explain_window().show()


PluginCommand.register_for_address("Explain Instruction", "", explain_instruction)
