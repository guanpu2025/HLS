"""extract_code: fences, truncation, fallback, and the four L1 regressions."""

from pathlib import Path

from agent.llm import extract_code, has_unclosed_fence

REPO = Path(__file__).resolve().parents[2]

TRUNCATED_SOLUTIONS = [
    REPO / "selftest/out/coder390/agent/he_c2hlsc_des/s0/solution.cpp",
    REPO / "selftest/out/coder390/agent/he_c2hlsc_overlapping/s0/solution.cpp",
    REPO / "selftest/out/coder390/agent/he_chstone_dfdiv/s0/solution.cpp",
    REPO / "selftest/out/coder390/agent/he_polybench_fixed_durbin/s0/solution.cpp",
]


def _assert_no_fence_lines(code: str) -> None:
    for i, line in enumerate(code.splitlines(), 1):
        assert not line.lstrip().startswith("```"), f"fence marker on line {i}: {line!r}"


def test_paired_cpp_fence():
    text = "说明\n```cpp\n#include \"a.h\"\nvoid foo() {}\n```\n完"
    code = extract_code(text)
    assert code.startswith("#include")
    assert "void foo()" in code
    _assert_no_fence_lines(code)


def test_longest_of_multiple_fences():
    text = (
        "```cpp\nint x;\n```\n"
        "```cpp\n#include \"k.h\"\nvoid kernel() { int y = 1; }\n```\n"
        "```c\nint z;\n```\n"
    )
    code = extract_code(text)
    assert "void kernel()" in code
    assert "int y = 1" in code
    assert "int x;" not in code
    assert "int z;" not in code
    _assert_no_fence_lines(code)


def test_open_fence_no_close_truncated():
    text = "```cpp\n#include \"des.h\"\nvoid DES() {\n    int ao = 0;\n    for (int i = 0; i < 32"
    assert has_unclosed_fence(text)
    code = extract_code(text)
    assert code.splitlines()[0] == '#include "des.h"'
    assert "void DES()" in code
    assert "for (int i = 0; i < 32" in code
    _assert_no_fence_lines(code)


def test_no_fence_but_looks_like_code():
    text = '#include "k.h"\n\nvoid top() { }\n'
    code = extract_code(text)
    assert code.startswith("#include")
    assert "void top()" in code
    _assert_no_fence_lines(code)


def test_fence_label_cxx():
    text = "```c++\n#include \"a.h\"\nvoid f() {}\n```\n"
    code = extract_code(text)
    assert "void f()" in code
    _assert_no_fence_lines(code)


def test_fence_label_hls():
    text = "```hls\n#include \"a.h\"\nvoid f() {}\n```\n"
    code = extract_code(text)
    assert "void f()" in code
    _assert_no_fence_lines(code)


def test_fence_label_empty():
    text = "```\n#include \"a.h\"\nvoid f() {}\n```\n"
    code = extract_code(text)
    assert "void f()" in code
    _assert_no_fence_lines(code)


def test_fallback_strips_leading_and_trailing_fence_lines():
    # Label "unknown" does not pair; fallback must still peel fence lines.
    text = "```unknown\n#include \"a.h\"\nvoid f() {}\n```\n"
    code = extract_code(text)
    assert code.splitlines()[0] == '#include "a.h"'
    assert "void f()" in code
    _assert_no_fence_lines(code)


def test_coder390_truncated_l1_solutions_first_line_is_not_fence():
    missing = [p for p in TRUNCATED_SOLUTIONS if not p.is_file()]
    assert not missing, f"missing regression fixtures: {missing}"
    for path in TRUNCATED_SOLUTIONS:
        raw = path.read_text(encoding="utf-8", errors="replace")
        assert raw.lstrip().startswith("```"), f"{path} is not a truncated-fence fixture"
        code = extract_code(raw)
        assert code, f"empty extract from {path}"
        first = code.splitlines()[0]
        assert not first.lstrip().startswith("```"), f"{path.name} first line still a fence: {first!r}"
        _assert_no_fence_lines(code)
