# 0019. "X presents Y" credits X

**Status:** Accepted. Refines [0008](0008-artist-identity.md).

## Context

Some lineup lines name a project, show or party next to the artist: "Ora Vance presents Night Garden", "Ora Vance & Juno Hale present: Tidewater". Treated as one name, each such line became its own "artist", split off from the real artist's other nights.

Most lines of this kind put the artist first and the project second. A few put a party or collective first and the artist second, and nothing in the wording reliably tells the two apart: both appear with and without a colon.

## Decision

- A line of the form **X present(s)[:] Y** credits **X**. Y is kept as the presented project, and the raw line is unchanged in `lineup_slots`.
- It only applies when something follows "present(s)", so a name that ends in the word ("… Present") stays whole.
- Set tags such as "(live)" are taken off first, so "X presents Y (live)" credits X with the tag live.
- Each side of a b2b is handled the same way.

## Consequences

- Artists who present a show get one identity for all their nights.
- A party presenting an artist is credited to the party. That is rare; a manual alias fixes it, and manual aliases survive rebuilds.
- Existing credits change only after `identify --rebuild`.

## Alternatives considered

- **Credit both sides.** Creates fake artists out of show and album titles.
- **Guess the direction from the colon or capitalisation.** Real lineups use both forms both ways.
