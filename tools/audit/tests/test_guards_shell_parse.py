"""shell_parse.py, which .claude/hooks/main_guard.py and .claude/hooks/subagent_guard.py read commands through,
finds every command a line runs. Command text is data here, never run; host names are fake."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guards_case import ROOT, run  # noqa: E402

sys.path.insert(0, str(ROOT / ".claude/hooks"))
import shell_parse  # noqa: E402

SUBAGENT_GUARD = ROOT / ".claude/hooks/subagent_guard.py"


def programs(text: str) -> list[tuple[str, ...]]:
    return [c.words for c in shell_parse.simple_commands(text) if c.words]


class SimpleCommands(unittest.TestCase):
    def test_separators_and_groups_split(self) -> None:
        self.assertEqual(programs("a 1; b && c || d | e & f\ng"),
                         [("a", "1"), ("b",), ("c",), ("d",), ("e",), ("f",), ("g",)])
        self.assertEqual(programs("(a; b) && { c; }"), [("a",), ("b",), ("c",)])
        self.assertEqual(programs("ls 2>&1 | head"), [("ls", "2>&1"), ("head",)])

    def test_quotes_keep_words_whole(self) -> None:
        self.assertEqual(programs("echo 'a; b' \"c | d\" e\\ f"), [("echo", "a; b", "c | d", "e f")])
        self.assertEqual(programs("echo a#; b"), [("echo", "a#"), ("b",)])     # '#' never hides text

    def test_substitutions_nested_and_in_double_quotes(self) -> None:
        self.assertIn(("x", "1"), programs("echo $(echo $(x 1))"))
        self.assertIn(("x", "1"), programs('echo "$(echo "$(x 1)")"'))
        self.assertIn(("x", "1"), programs("echo `echo \\`x 1\\``"))
        self.assertIn(("x", "1"), programs("diff <(x 1) b"))
        self.assertNotIn(("x", "1"), programs("echo '$(x 1)'"))                 # single quotes do not expand

    def test_wrappers_and_keywords_are_removed(self) -> None:
        for line in ("env -u A B=1 x 1", "nohup x 1", "time -p x 1", "timeout -k 5 -s KILL 10 x 1",
                     "sudo -u pi -g g x 1", "nice -n 5 x 1", "exec -a n x 1", "command x 1", "builtin x 1",
                     "stdbuf -o L x 1", "caffeinate -t 5 x 1", "uv run --with a x 1", "if x 1; then :; fi",
                     "while x 1; do :; done", "until x 1; do :; done", "! x 1", "{ x 1; }", "eval 'x 1'",
                     "watch -n 2 'x 1'", "bash -c 'x 1'", "sh -ec 'x 1'", "zsh -o err -c 'x 1'", "bash s.sh",
                     "for h in a; do x 1; done", "xargs -I {} -P 2 x 1", "find . -exec x 1 \\;"):
            with self.subTest(line=line):
                found = programs(line)
                want = ("s.sh",) if line == "bash s.sh" else ("x", "1")
                self.assertIn(want, found)

    def test_assignments_and_input_words_are_marked(self) -> None:
        last = shell_parse.simple_commands("A=1 B='2 3' bash -c 'x'")[-1]
        self.assertEqual((last.words, dict(last.assigned)), (("x",), {"A": "1", "B": "2 3"}))
        only = shell_parse.simple_commands("HOSTS=--pi")[0]
        self.assertEqual((only.words, dict(only.assigned)), ((), {"HOSTS": "--pi"}))
        self.assertTrue(shell_parse.simple_commands("echo a | xargs -I{} x {}")[-1].from_input)
        self.assertTrue(shell_parse.simple_commands("find . -exec x {} +")[-1].from_input)
        self.assertFalse(shell_parse.simple_commands("x {}")[-1].from_input)

    def test_heredoc_bodies_are_input_not_commands(self) -> None:
        cmds = shell_parse.simple_commands("cat <<'EOF' | y\nit's x 1\nEOF\nz")
        self.assertEqual([c.words for c in cmds], [("cat",), ("y",), ("z",)])
        self.assertEqual(cmds[0].stdin, "it's x 1")
        self.assertIn(("x", "1"), programs("cat <<EOF\n$(x 1)\nEOF"))        # an unquoted body expands
        self.assertNotIn(("x", "1"), programs("cat <<'EOF'\n$(x 1)\nEOF"))
        self.assertIn(("x", "1"), programs("bash <<EOF\nx 1\nEOF"))           # a shell runs its body
        self.assertIn(("git", "commit", "-m"), [c.words[:3] for c in shell_parse.simple_commands(
            "git commit -m \"$(cat <<'EOF'\nit's done\nEOF\n)\"")])

    def test_unbalanced_lines_raise_and_the_rough_split_still_reads_them(self) -> None:
        for line in ("echo 'a", 'echo "a', "echo $(a", "echo `a", "echo $(a 'b)", "cat <<"):
            with self.subTest(line=line), self.assertRaises(shell_parse.ParseError):
                shell_parse.simple_commands(line)
        self.assertIn(("x", "1"), [c.words for c in shell_parse.rough_commands("echo 'a; x 1")])

    def test_deep_nesting_raises_too_deep(self) -> None:
        line = "x"
        for _ in range(shell_parse.MAX_DEPTH + 2):
            line = f"echo $({line})"
        self.assertRaises(shell_parse.TooDeep, shell_parse.simple_commands, line)


class SubagentGuardThroughTheParser(unittest.TestCase):
    """Forms the shared parser added to the subagent guard."""

    def test_more_forms_are_blocked(self) -> None:
        for command in ("echo $(echo $(git push))", 'echo "$(git push)"', "bash <<EOF\ngit push\nEOF",
                        "time -p git push", "nice -n 5 git push", "echo x | xargs -n1 git push",
                        "echo $(make deploy-layout", "ssh fakepi.test 'cat x"):
            with self.subTest(command=command):
                self.assertEqual(run(SUBAGENT_GUARD, command, str(ROOT)).returncode, 2)

    def test_heredoc_text_and_searches_pass(self) -> None:
        for command in ("cat > /tmp/notes.txt <<'EOF'\ngit push is the main session's\nEOF",
                        "grep -rn 'git push' docs", "echo ssh", "ssh fakepi.test uptime"):
            with self.subTest(command=command):
                done = run(SUBAGENT_GUARD, command, str(ROOT))
                self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
