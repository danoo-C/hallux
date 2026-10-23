# hpm: the Hallux package manager

One place on your PC for the apps you build in Hallux worlds, and for their packs,
characters and memories. You build an app in one world, publish it once, and install or
update it into any other world, or a friend's, without asking the AI for an install file
each time.

| Document | What it is | Status |
|---|---|---|
| [hpm.md](hpm.md) | Packages, the store on your PC, publishing, installing with options, conflicts, what a world remembers of it, telling the machine | Proposed 2026-10-23; questions open |
| [migrations.md](migrations.md) | When an app changes how it stores its data: data formats, migrations the AI writes and runs, the backup and the checks around it | Proposed 2026-10-23; questions open |
| [sharing.md](sharing.md) | Publishing to friends: stores on GitHub, `hpm push`, privacy, and packages as instructions to the AI | Proposed 2026-10-23; questions open |

There is no code and no plan yet. The plan comes after the questions in the three
documents are decided.

## Where it came from

The user kept building an app in one world (kittystory in `test-hallux`) and then asking
the machine for an installation or update file (`kittystory-web.update`,
`kittysongs.package`), going back and forth. They asked for "a manager global for every
hallux world on my pc": `hpm install kittystory`, with install options as checkboxes
(`[x] kittystory, [x] packs, [ ] memories`), and a question when packs are already
installed ("add and overwrite them or skip?").

Three things were decided in the conversation that led here (2026-10-23):

1. **A store on the PC, above every world, and checkboxes at install.** The user's own
   idea; [hpm.md](hpm.md).
2. **The AI is involved.** The user: "i think the AI should be involved. lets say i do a
   drastic change on how kittystory stores characters. if you update then you loose all
   the characters." The answer is [migrations.md](migrations.md).
3. **Sharing with friends, not the whole world.** Of three levels offered (only your PC,
   friends, a public store), the user chose level 2, friends; [sharing.md](sharing.md).
