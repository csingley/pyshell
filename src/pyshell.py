#!/usr/bin/env python3
""" Toy UNIX shell implemented in Python as systems programming exercise.

~~Be the Shell~~

'''
The shell operates according to the following general overview of operations.
The specific details are included in the cited sections of this chapter.

1. The shell reads its input from a file (see sh), from the -c option or from
   the system() and popen() functions defined in the System Interfaces volume
   of POSIX.1-2017. If the first line of a file of shell commands starts with
   the characters "#!", the results are unspecified.

2. The shell breaks the input into tokens: words and operators; see Token Recognition.

3. The shell parses the input into simple commands (see Simple Commands) and
   compound commands (see Compound Commands).

4. The shell performs various expansions (separately) on different parts of
   each command, resulting in a list of pathnames and fields to be treated as a
   command and arguments; see wordexp.

5. The shell performs redirection (see Redirection) and removes redirection
   operators and their operands from the parameter list.

6. The shell executes a function (see Function Definition Command), built-in
   (see Special Built-In Utilities), executable file, or script, giving
   the names of the arguments as positional parameters numbered 1 to n, and the
   name of the command (or in the case of a function within a script, the name
   of the script) as the positional parameter numbered 0 (see Command Search and
   Execution).

7. The shell optionally waits for the command to complete and collects the exit
   status (see Exit Status for Commands).

[...]

The order of word expansion shall be as follows:

1. - Tilde expansion (see Tilde Expansion),
   - parameter expansion (see Parameter Expansion),
   - command substitution (see Command Substitution), and
   - arithmetic expansion (see Arithmetic Expansion)
   shall be performed, beginning to end. See item 5 in Token Recognition.

2. Field splitting (see Field Splitting) shall be performed on the portions of
   the fields generated by step 1, unless IFS is null.

3. Pathname expansion (see Pathname Expansion) shall be performed, unless
   `set -f` is in effect.

4. Quote removal (see Quote Removal) shall always be performed last.
'''

https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html

Also cf.
https://www.cs.purdue.edu/homes/grr/SystemsProgrammingBook/Book/Chapter5-WritingYourOwnShell.pdf
"""
from __future__ import annotations
import dataclasses
import glob
import os
import re
import shlex


STDIN = 0
STDOUT = 1
STDERR = 2


class FinalBackslash(Exception):
    """Exception raised when lexing a line with a naked final backslash"""


@dataclasses.dataclass(frozen=True)
class Command:
    name: str
    args: tuple[str]

    @classmethod
    def from_tokens(cls, tokens: list[str]) -> Command:
        """ Construct instance from sequence of lexical tokens. """

        return cls(name=tokens[0], args=tokens)


@dataclasses.dataclass(frozen=True)
class CommandSequence:
    """ Command pipeline with optional I/O redirection.
    {in,out,err}file are file descriptors, i.e. integers as known to OS.
    """

    commands: tuple[Command]
    infile: int = STDIN
    outfile: int = STDOUT
    errfile: int = STDERR


procctlRE = re.compile(r"([|&<>]{1,2})")
""" Add whitespace around unescaped process control operators so that
`shlex.split()` will do the right thing. """


redirectInput = r"\d?<[^<].*"
redirectInputRE = re.compile(redirectInput)
""" Sec. 2.7.1 (Redirecting Input) """


redirectOutput = r"\d?(>|>\|)[^>].*"
redirectOutputRE = re.compile(redirectOutput)
""" Sec. 2.7.2 (Redirecting Output) """


appendRedirectOutput = r"\d?>>[^>].*"
appendRedirectOutputRE = re.compile(appendRedirectOutput)
""" Sec. 2.7.3 (Appending Redirected Output) """


hereDoc = r"\d?(<<|<<-[^<-].*)"
hereDocRE = re.compile(hereDoc)
""" Sec. 2.7.4 (Here-Document) """


duplicateInput = r"\d?<&[^&].*"
duplicateInputRE = re.compile(duplicateInput)
""" Sec. 2.7.5 (Duplicating an Input File Descriptor) """


duplicateOutput = r"\d?>&[^&].*"
duplicateOutputRE = re.compile(duplicateOutput)
""" Sec. 2.7.6 (Duplicating an Output File Descriptor) """


inputOutput = r"\d?<>[^>].*"
inputOutputRE = re.compile(inputOutput)
""" Sec. 2.7.7 (Open File Descriptors for Reading and Writing) """


def lex(line: str):
    """ Process full logical cmd line into lexical tokens.

    * Sec. 2.6.5 (Field Splitting)
    """

    try:
        tokens = shlex.split(line)
    except ValueError as err:
        #  In shell grammar, final naked backslash means line continuation.
        if err.args[0] == "No escaped character":
            assert line.endswith("\\")
            raise FinalBackslash
        raise

    return tokens


def parse(tokens: list[str]) -> CommandSequence:
    """ Parse lexical tokens into CommandSequence.

    * Sec. 2.6.6 (Pathname Expansion)
    * Sec. 2.6.7 (Quote Removal) - @@FIXME
    * Sec. 2.7 (Redirection) - @@FIXME
    * Sec. 2.9 (Shell Commands)
    """

    args = []; cmds = []
    for token in tokens:
        if token == "|":
            cmds.append(Command.from_tokens(args))
            args = []
        else:
            #  * Sec 2.6.6 (Pathname Expansion)
            if any(char in token for char in "?*"):
                expanded = glob.glob(token)
            else:
                expanded = [token]
            args.extend(expanded)

    if args:
        #  * Sec. 2.7 (Redirection)
        #  Stitch tokens back together so we can process with regex
        stitched = " ".join(args)
        cmds.append(Command.from_tokens(args))

    return CommandSequence(commands=cmds)


def main(prompt: str = "& "):
    """ Read/evaluate/print loop. """

    default_prompt = prompt
    logical_line = ""

    while True:
        #  Read input
        try:
            line = input(prompt)
            #  Word expansions
            #  * Sec. 2.6.1 (Tilde Expansion)
            #  * Sec. 2.6.2 (Parameter Expansion)
            for fn in os.path.expanduser, os.path.expandvars:
                line = fn(line)
            #  * Sec. 2.6.3 (Command Substition) - @@FIXME
            #  * Sec. 2.6.4 (Arithmetic Expansion) - @@FIXME

            # Add whitespace around unescaped process control operators so that
            # `shlex.split()` will do the right thing.
            line = procctlRE.sub(r" \1 ", line)
        except EOFError:
            #  Handle Ctrl-d
            if not logical_line:
                print("\nThanks for playing; please come back soon.")
                raise SystemExit
            line = ""

        #  Lex
        #  * Sec. 2.6.5 (Field Splitting)
        try:
            tokens = lex(logical_line + line)
            logical_line = ""
            prompt = default_prompt
        except FinalBackslash:
            # In shell grammar, final naked backslash means line continuation.
            logical_line += line[:-1]
            prompt = "> "
            continue

        #  * Sec. 2.6.6 (Pathname Expansion)
        #  * Sec. 2.6.7 (Quote Removal) - @@FIXME
        #  * Sec. 2.7 (Redirection) - @@FIXME
        cmdseq = parse(tokens)

        cmds = cmdseq.commands
        if not cmds:
            continue
        last_cmd = cmds[-1]

        #  Fork/exec
        child_stdin = next_child_stdin = STDIN

        for cmd in cmds:
            if cmd is last_cmd:
                child_stdout = STDOUT
            else:
                #  Create new pipe to communicate with next subprocess
                next_child_stdin, child_stdout = os.pipe()

            child_pid = os.fork()
            if not child_pid:  # I am the child
                child_exec(cmd=cmd, stdin=child_stdin, stdout=child_stdout)
                #  We should never reach here
                assert True is False

            #  Else I am the parent
            if child_stdout != STDOUT:
                os.close(child_stdout)
            #  Promote next_child_stdin to child_stdin for next iteration
            child_stdin = next_child_stdin

        #  Clean up & wait
        if child_stdin != STDIN:
            os.close(child_stdin)
        child_pid, status = os.waitpid(child_pid, 0)
        exitcode = os.waitstatus_to_exitcode(status)


def child_exec(cmd: Command, stdin: int, stdout: None):
    """ """
    if stdin != STDIN:
        os.dup2(stdin, STDIN)
    if stdout != STDOUT:
        os.dup2(stdout, STDOUT)
    try:
        os.execvp(file=cmd.name, args=cmd.args)
    except FileNotFoundError:
        raise SystemExit(f"{cmd.name}: command not found")


if __name__ == "__main__":
    main()
