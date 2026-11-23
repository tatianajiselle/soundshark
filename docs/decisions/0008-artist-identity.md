# 0008. Artist names: exact matches merge, fuzzy matches wait for a human

**Status:** Accepted

## Context

The same DJ appears as "Ora Vance", "ORA VANCE" and "Ora  Vance (live)". Different DJs can also look alike: two names a few letters apart, or a name with an extra word, may well be different people. A wrong merge is worse than a missed one, because it mixes two people's connections together and quietly corrupts every score around them.

## Decision

- **Normalize** every name the same way: lowercase, remove accents, collapse punctuation and spaces (a hyphen or a dot counts as a space, so "Dax-Ferro" is "Dax Ferro" and "D.Ferro" is "D Ferro"), and strip set tags such as "(live)" into the slot's tags.
- **Exact matches after normalization merge automatically.** Each normalized spelling is an alias that belongs to exactly one artist.
- **Fuzzy matches are only suggestions.** Close pairs are scored and listed for review, and a person approves or rejects them from the command line. Nothing fuzzy merges on its own.
- **Manual decisions always win** over automatic ones, and survive rebuilds.
- Very short or very common names are flagged as possibly ambiguous, to be scoped by city later.

## Consequences

- The graph starts out slightly fragmented (some duplicates), and gets better as suggestions are reviewed.
- Merges are deliberate and reversible.
- There is a small, ongoing review chore. The tooling has to make it quick.

## Alternatives considered

- **Auto-merge above a similarity threshold.** Faster, but some merges would be wrong and hard to spot afterwards.
- **External identifiers only.** Many underground artists simply don't have one.
