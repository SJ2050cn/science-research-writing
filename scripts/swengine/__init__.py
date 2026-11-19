"""The step engine. Every run command goes through a Run (run.py):

cli            argument parsing and command dispatch (the only module that prints)
run            the Run: start, open, response, submit, resume, abandon; the joined step table
submission     a submitted result against its step's expect, one checker per field type
workflow       step definitions, the plan line, the run state, the section steps
wholepaper     whole-paper runs: the split step and the sections, one sub-state each
profile_flows  the profile steps and the scan-profile and study-profile tasks
guard          the Stop hook and the Codex setup step
runstore       project root, run folders, state.json on disk
classify       markup, mode and section from the input; whole-paper splits
check, modes   the integrity checker, and what differs per mode
render, rules  output templates; rule names in the reference files
fields, errors closed-list validation of start's fields; exit codes and refusals
profile, codexhook   the style profile file; the Codex hooks file
The data they share lives in references/workflow.json.
"""
