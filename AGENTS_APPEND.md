# AGENTS.md addition — deterministic command batching

Append the paragraph below to an existing `AGENTS.md` (or a global Codex guidance file). Do not replace repository-specific instructions.

When two or more shell commands are already known and can execute consecutively without further model decisions, use `delayed-seq -- 'command 1' 'command 2'`. Sequential dependencies such as formatting before testing are valid: the wrapper executes commands in order and stops on failure. Use ordinary commands for single operations, initial exploration, or when the next command requires interpreting the previous result. Do not generate custom delay, polling, or sequencing Bash. Preserve required validation and never assume incomplete edits succeeded.
