from hallux.protocol import Field, Reply, decode, envelope, parse


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


FORM_REPLY = '''<screen>
  GNU nano 7.2        hello.txt
</screen><prompt></prompt><form keys="C-o C-x C-w" focus="text" keymap="nano">
<editor id="text" top="3" height="20" width="120" file="/home/user/hello.txt" cursor="2:5" style="fg:#ffb6c1" lang="python"/>
<line id="name" top="23" left="21" width="60">hello.txt</line>
<pager id="man">
a < b && c > d </pager>
<editor id="empty"></editor>
</form>'''


def test_parse_a_form():
    reply = parse(FORM_REPLY)
    assert reply.screen == "  GNU nano 7.2        hello.txt\n" and reply.prompt == ""
    form = reply.form
    assert form.keys == ("C-o", "C-x", "C-w") and form.focus == "text" and form.keymap == "nano"
    editor, line, pager, empty = form.fields
    assert editor == Field("editor", "text", top=3, left=1, width=120, height=20, text=None,
                           file="/home/user/hello.txt", cursor=(2, 5), style="fg:#ffb6c1",
                           lang="python")
    assert (line.kind, line.text, line.height, line.width) == ("line", "hello.txt", 1, 60)
    assert pager.text == "a < b && c > d "             # the body is literal text
    assert (pager.width, pager.height) == (0, 0)       # 0: to the edge of the screen
    assert empty.text == ""                            # empty body: empty; <x/>: keep


def test_forms_only_count_after_the_prompt():
    reply = parse('<screen>\n<form keys="q"><line id="a">hi</line></form>\n</screen><prompt>$ </prompt>')
    assert reply.form is None and reply.screen.startswith("<form")   # cat of an HTML file
    assert parse('<screen>\n</screen><prompt></prompt><form keys="q"></form>').form is None
    assert parse('<screen>\n</screen><prompt></prompt><form><line top="x">a</line></form>').form is None


def test_bad_form_values_fall_back():
    form = parse('<screen>\n</screen><prompt></prompt><form keymap="emacsvi">'
                 '<line id="a" top="x" cursor="nope">a</line></form>').form
    assert form.keymap == "emacs" and form.fields[0].top == 1 and form.fields[0].cursor is None
