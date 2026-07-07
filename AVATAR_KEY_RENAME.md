# Avatar key rename — mobile side (CuedUp/)

The backend keys were renamed to match the new display names. The mobile app
(`CuedUp/`) is **not** in this checkout, so its side must be changed by hand.
Ship all three together (backend, migration, mobile) or avatar images break.

## Old key -> new key (18 renames; the other 14 keys are unchanged)

| Old key    | New key             | Display name        |
|------------|---------------------|---------------------|
| couch      | couch_potato        | Couch Potato        |
| popcorn    | popcorn_enthusiast  | Popcorn Enthusiast  |
| host       | concierge           | Concierge           |
| ticket     | golden_ticket       | Golden Ticket       |
| shoes      | ruby_slippers       | Ruby Slippers       |
| shorts     | carls_boxers        | Carl's Boxers       |
| ball       | wilson              | Wilson!             |
| house      | up                  | Up!                 |
| ranger     | space_ranger        | Space Ranger        |
| noir       | detective           | Detective           |
| blade      | the_force           | The Force           |
| hammer     | mjolnir             | Mjolnir *           |
| idol       | golden_idol         | Golden Idol         |
| wizard     | merlin              | Merlin              |
| vampire    | dracula             | Dracula             |
| raptor     | clever_girl         | Clever Girl         |
| gauntlet   | infinity_gauntlet   | Infinity Gauntlet   |
| ring       | the_one_ring        | The One Ring        |

\* Backend display name uses "Mjolnir" with an accent (Mjolnir). Check the app
font renders it before shipping, or drop the accent.

Unchanged keys: bookworm, punk, poet, anchor, dj, donut, librarian, professor,
hoverboard, rockstar, diva, conductor, totem, director.

## What to change in CuedUp/src/avatars.ts

1. The key in the avatar map object (the property the backend `avatar_key`
   indexes into) must be renamed to the new key for all 18 rows.
2. If the bundled PNG filenames are named after the key (e.g. `couch.png`),
   rename the files AND their `require(...)`/`import` paths to match
   (`couch_potato.png`). If the map points at arbitrary filenames, only the
   object key changes and the PNGs can stay as-is.

## Ship order

1. Merge backend + migration, deploy (`flask db upgrade` runs on container start).
2. Ship the matching mobile build.

Between step 1 and step 2, existing users' stored keys are the NEW keys while an
old app build still looks up OLD keys -> those users see a blank/default avatar
until they update. For an internal TestFlight beta that's cosmetic and
self-heals on app update, but if you want zero flicker, release the mobile build
first-ish or at the same time.
