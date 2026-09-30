from hallux.protocol import Reply, decode, envelope, parse


def test_envelope():
    assert envelope("boot", cwd="/", cols=80) == '<boot cwd="/" cols="80"></boot>'
    assert envelope("input", "ls -la | grep x", cwd='/a "b"') == \
        '<input cwd="/a &quot;b&quot;">ls -la | grep x</input>'


def test_decode_control_pictures():
    assert decode("␛[1;35mcow␛[0m> ") == "\x1b[1;35mcow\x1b[0m> "
    assert decode("␛]0;hallux␇") == "\x1b]0;hallux\x07"
    assert decode("50%␍100%␡") == "50%\r100%\x7f"
    assert decode("plain ✓ ž") == "plain ✓ ž"


def test_parse_a_normal_reply():
    reply = parse("<screen>\nfib.py  notes.md\n</screen><prompt>user@hallux:~$ </prompt>")
    assert reply == Reply(screen="fib.py  notes.md\n", prompt="user@hallux:~$ ")


def test_parse_keeps_output_exact():
    assert parse("<screen>\n</screen><prompt>$ </prompt>").screen == ""          # no output
    assert parse("<screen>\n\n</screen><prompt>$ </prompt>").screen == "\n"      # echo
    assert parse("<screen>\nno newline</screen><prompt>$ </prompt>").screen == "no newline"
    assert parse("<screen>\n< moo >\n</screen><prompt>$ </prompt>").screen == "< moo >\n"


def test_parse_decodes_prompt_and_screen():
    reply = parse("<screen>\n␛[H␛[2J</screen><prompt>␛[35mmoo>␛[0m </prompt>")
    assert reply.screen == "\x1b[H\x1b[2J" and reply.prompt == "\x1b[35mmoo>\x1b[0m "


def test_parse_control_tags():
    assert parse("<screen>\nlogout\n</screen><prompt></prompt><halt/>").halt
    assert parse("<screen>\n</screen><prompt></prompt><reboot/>").reboot
    assert parse('<screen>\n</screen><prompt></prompt><tty mode="raw"/>').tty == "raw"
    assert not parse("<screen>\n<halt/>\n</screen><prompt>$ </prompt>").halt  # output, not a tag


def test_parse_survives_a_broken_format():
    assert parse("Let me check.<screen>\nx\n</screen><prompt>$ </prompt>").screen == "x\n"
    assert parse("<screen>\nx\n<prompt>$ </prompt>") == Reply(screen="x\n", prompt="$ ")
    assert parse("<screen>\nx\n</screen>") == Reply(screen="x\n", prompt=None)
    assert parse("just text") == Reply(screen="just text", prompt=None)
