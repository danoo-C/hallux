from hallux.protocol import Field, Form, Reply, decode, envelope, parse, resolve


def test_envelope():
    assert envelope("boot", cwd="/", cols=80) == '<boot cwd="/" cols="80"></boot>'
    assert envelope("input", "ls -la | grep x", cwd='/a "b"') == \
        '<input cwd="/a &quot;b&quot;">ls -la | grep x</input>'


def test_decode_control_pictures():
    assert decode("␛[1;35mcow␛[0m> ") == "\x1b[1;35mcow\x1b[0m> "
    assert decode("␛]0;hallux␇") == "\x1b]0;hallux\x07"
    assert decode("50%␍100%␡") == "50%\r100%"                 # DEL has no use on screen
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
    assert editor == Field("editor", "text", top=3, left=None, width=120, height=20, text=None,
                           file="/home/user/hello.txt", cursor=(2, 5), style="fg:#ffb6c1",
                           lang="python")
    assert (line.kind, line.text, line.height, line.width) == ("line", "hello.txt", None, 60)
    assert pager.text == "a < b && c > d "             # the body is literal text
    assert (pager.width, pager.height) == (None, None)  # not given
    assert (pager.with_defaults().width, pager.with_defaults().height) == (0, 0)   # to the edge
    assert line.with_defaults().height == 1
    assert empty.text == ""                            # empty body: empty; <x/>: keep


def test_forms_only_count_after_the_prompt():
    reply = parse('<screen>\n<form keys="q"><line id="a">hi</line></form>\n</screen><prompt>$ </prompt>')
    assert reply.form is None and reply.screen.startswith("<form")   # cat of an HTML file
    assert parse('<screen>\n</screen><prompt></prompt><form keys="q"></form>').form is None
    assert parse('<screen>\n</screen><prompt></prompt><form><line top="x">a</line></form>').form is None


def test_bad_form_values_fall_back():
    form = parse('<screen>\n</screen><prompt></prompt><form keymap="emacsvi">'
                 '<line id="a" top="x" cursor="nope">a</line></form>').form
    assert form.keymap == "emacs" and form.fields[0].cursor is None
    assert form.fields[0].top is None and form.fields[0].with_defaults().top == 1


def test_the_ai_can_rewrite_the_typed_line():
    assert parse("<screen>\n</screen><prompt>$ </prompt><edit>cat /etc/</edit>").edit == "cat /etc/"
    assert parse("<screen>\n</screen><prompt>$ </prompt><edit></edit>").edit == ""
    assert parse("<screen>\n</screen><prompt>$ </prompt>").edit is None


def form_of(reply):
    return parse("<screen>\n</screen><prompt></prompt>" + reply).form


def test_a_kept_field_keeps_what_the_ai_does_not_restate():
    """The live bug: after ^X, <editor id="text"/> jumped to the top-left and covered nano."""
    opened, to_load = resolve(form_of(
        '<form keys="C-x"><editor id="text" top="2" left="1" height="46" width="0" '
        'file="hello.txt"></editor></form>'), {})
    assert to_load == {"text"}                                  # a new field: load its file
    on_screen = {f.id: f for f in opened.fields}
    save_prompt, to_load = resolve(form_of(
        '<form keys="C-c"><editor id="text"/>'
        '<line id="yn" top="48" left="23" width="20" style="bg:#ffffff"></line></form>'), on_screen)
    editor, yn = save_prompt.fields
    assert (editor.top, editor.left, editor.height, editor.width) == (2, 1, 46, 0)
    assert editor.file == "hello.txt" and editor.text is None   # keeps the user's text
    assert to_load == set()                                     # ... and never reloads it
    assert (yn.top, yn.left, yn.height, yn.text) == (48, 23, 1, "")


def test_repeating_the_file_keeps_unsaved_edits_but_a_new_file_loads():
    on_screen = {"text": Field("editor", "text", top=2, file="a.txt").with_defaults()}
    same, to_load = resolve(form_of('<form><editor id="text" file="a.txt"></editor></form>'), on_screen)
    assert to_load == set() and same.fields[0].text is None
    other, to_load = resolve(form_of('<form><editor id="text" file="b.txt"/></form>'), on_screen)
    assert to_load == {"text"} and other.fields[0].file == "b.txt"
    replaced, to_load = resolve(form_of('<form><editor id="text">new text</editor></form>'), on_screen)
    assert to_load == set() and replaced.fields[0].text == "new text"


def test_forms_can_have_a_footer_and_rows_from_the_bottom():
    form = form_of('<form keys="C-x"><footer>\n␛[7m^X␛[0m Exit\n^O Write\n</footer>'
                   '<editor id="t" top="3" height="0"/><line id="yn" top="-3" left="23"></line></form>')
    assert form.footer == "\x1b[7m^X\x1b[0m Exit\n^O Write\n"
    editor, yn = form.fields
    assert (editor.top, editor.height) == (3, 0) and yn.top == -3
    assert yn.with_defaults().top == -3 and Field("line", "x").with_defaults().top == 1



def test_the_ai_can_change_the_working_directory():
    assert parse("<screen>\n</screen><prompt>$ </prompt><cwd>/home/user</cwd>").cwd == "/home/user"
    assert parse("<screen>\n</screen><prompt>$ </prompt><cwd> </cwd>").cwd is None
    assert parse("<screen>\n</screen><prompt>$ </prompt>").cwd is None


# ---------------------------------------------------------------- streaming

from hallux.protocol import ScreenStream  # noqa: E402


def streamed(reply, size):
    stream, pieces = ScreenStream(), []
    for i in range(0, len(reply), size):
        pieces.append(stream.feed(reply[i:i + size]))
    return stream, pieces


def test_streaming_shows_exactly_the_final_screen_at_any_chunk_size():
    reply = ("Let me check.<screen>\n␛[34mfib.py␛[0m  notes.md\n␛]0;title␇done\n</screen>"
             "<prompt>$ </prompt><cwd>/tmp</cwd>")
    for size in range(1, 12):
        stream, pieces = streamed(reply, size)
        assert "".join(pieces) == parse(reply).screen and stream.rest(parse(reply).screen) == ""
        assert all("<" not in piece for piece in pieces)        # never a bit of </screen>


def test_escape_sequences_are_never_split():
    stream = ScreenStream()
    stream.feed("<screen>\nred ␛[3")
    assert stream.shown == "red "                               # the half sequence waits
    assert stream.feed("1mx") == "\x1b[31mx"


def test_a_form_first_reply_does_not_stream():
    stream, pieces = streamed('\n<form keys="C-x"><editor id="t"/></form><screen>\nnano\n</screen>', 4)
    assert "".join(pieces) == "" and stream.state == "off"


def test_rest_notices_a_different_final_screen():
    stream, _ = streamed("<screen>\nhello\n</screen>", 3)
    assert stream.rest("hello\nworld\n") == "world\n" and stream.rest("bye\n") is None


def test_form_first_replies_parse():
    reply = parse('<form keys="C-x"><footer>\n^X Exit\n</footer><editor id="t" top="2"/></form>'
                  '<screen>\n  GNU nano\n</screen><prompt></prompt>')
    assert reply.screen == "  GNU nano\n" and reply.prompt == ""
    assert reply.form.keys == ("C-x",) and reply.form.footer == "^X Exit\n"


def test_color_codes_that_lost_their_escape_are_repaired():
    """Live: a long boot log came with "[38;5;218m" instead of "␛[38;5;218m"."""
    assert decode("[38;5;218m[    0.000000] Linux[0m") == "\x1b[38;5;218m[    0.000000] Linux\x1b[0m"
    assert decode("[  OK  ] ssh [main] [5 files] [x]") == "[  OK  ] ssh [main] [5 files] [x]"
    shown = r"PS1='\[\e[38;5;205m\]' echo -e \033[1m \x1b[2m"   # spelled out: stays text
    assert decode(shown) == shown
    assert decode("␛[31mred") == "\x1b[31mred"                          # no double escape


def test_repaired_codes_stream_exactly_like_the_final_screen():
    reply = "<screen>\n[38;5;218m[  OK  ][0m ssh\nPS1='\\[\\e[31m\\]'\n␛[1mbold␛[0m\n</screen><prompt>$ </prompt>"
    for size in range(1, 15):
        stream, pieces = streamed(reply, size)
        assert "".join(pieces) == parse(reply).screen


# ---------------------------------------------------------------- what may reach your terminal

from hallux.protocol import safe  # noqa: E402


def test_harmless_codes_pass():
    harmless = ("\x1b[1;35mpink\x1b[0m\x1b[H\x1b[2J\x1b[3J\x1b[2A\x1b[10;5H\x1b[K\x1b7\x1b8"
                "\x1b[?25l\x1b[?25h\x1b]0;user@hallux: ~\x07\a\b\t\r\n")
    assert safe(harmless) == harmless


def test_risky_codes_are_dropped():
    assert safe("a\x1b]52;c;cm0gLXJmIC8K\x07b") == "ab"                    # clipboard write
    assert safe("\x1b]8;;https://x\x1b\\link\x1b]8;;\x1b\\") == "link"     # hidden link target
    assert safe("\x1b[6n\x1b[c\x1b[>c\x1b[21t\x1b[5n\x1b[?1$p") == ""       # answer-back queries
    assert safe("\x1b[1;5r\x1b[?1049h\x1b[?1000h\x1b[>1u\x1b[?2004h") == ""  # modes and keyboard
    assert safe("\x1bP+q544e\x1b\\\x1b_Gimage\x1b\\\x1bc") == ""            # DCS, APC, reset
    assert safe("x\x05y\x9bz\x0ew") == "xyzw"                              # ENQ, C1, shift-out


def test_a_clipboard_write_split_across_streamed_pieces_is_still_dropped():
    reply = "<screen>\nok␛]52;c;cm0gLXJm␇done ␛[31mred␛[0m\n</screen><prompt>$ </prompt>"
    assert parse(reply).screen == "okdone \x1b[31mred\x1b[0m\n"
    for size in range(1, 21):
        stream, pieces = streamed(reply, size)
        assert "".join(pieces) == parse(reply).screen


def test_raw_forms():
    form = form_of('<form raw="yes" tick="3"><footer>\nq quit\n</footer></form>')
    assert form.raw and form.tick == 3 and form.fields == () and form.footer == "q quit\n"
    assert form_of('<form raw="yes" tick="0.1"></form>').tick == 1          # at most once a second
    assert form_of('<form raw="yes" tick="soon"></form>').tick == 0
    assert form_of('<form tick="3"><line id="a">x</line></form>').tick == 0  # ticks are for raw mode
    assert form_of('<form keys="q"></form>') is None                        # no fields, not raw
