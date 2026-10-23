# hpm: the Hallux package manager

One place on your PC for the apps you build in Hallux worlds, and for their packs,
characters and memories. You build an app in one world, publish it once, and install or
update it into any other world, or a friend's, without asking the AI for an install file
each time.

**The design is done** (the user, 2026-10-23: "the design doc can be declared done"). The
open questions at the end of each document still have only recommendations; they are
decided together with the plan, which comes next. No code yet.

| Document | What it is | Status |
|---|---|---|
| [hpm.md](hpm.md) | Packages, the store on your PC, publishing, installing with options, many packages at once, conflicts, what a world remembers of it, telling the machine, the panel's Packages tab | Done; 8 open questions |
| [migrations.md](migrations.md) | When an app changes how it stores its data: data formats, migrations the AI writes and runs, the backup and the checks around it | Done; 4 open questions |
| [sharing.md](sharing.md) | Publishing to friends: stores on GitHub, `hpm push`, privacy, and packages as instructions to the AI | Done; 5 open questions |

## Where it came from

The user kept building an app in one world (kittystory in `test-hallux`) and then asking
the machine for an installation or update file (`kittystory-web.update`,
`kittysongs.package`), going back and forth. They asked for "a manager global for every
hallux world on my pc": `hpm install kittystory`, with install options as checkboxes
(`[x] kittystory, [x] packs, [ ] memories`), and a question when packs are already
installed ("add and overwrite them or skip?").

What was decided in the conversation that led here (2026-10-23):

1. **A store on the PC, above every world, and checkboxes at install.** The user's own
   idea; [hpm.md](hpm.md).
2. **The AI is involved.** The user: "i think the AI should be involved. lets say i do a
   drastic change on how kittystory stores characters. if you update then you loose all
   the characters." The answer is [migrations.md](migrations.md).
3. **Sharing with friends, not the whole world.** Of three levels offered (only your PC,
   friends, a public store), the user chose level 2, friends; [sharing.md](sharing.md).
4. **The panel's Packages tab.** The user: "i exceptionally like the packages tab"
   ([hpm.md](hpm.md), section 10). The plan should weigh it accordingly.
5. **Many packages in one command.** A whole store or a bundle on one screen
   ([hpm.md](hpm.md), section 6a). The user: "this sound so much better than what i
   innitially proposed. I LIKE IT".
