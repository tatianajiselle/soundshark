# wavelength 〰️

Map a music scene. **wavelength** crawls DJ lineups (past and upcoming) into a graph of who plays with whom, then listens to the music to find who's really on the same wavelength.

> Work in progress, built in the open as a way to learn async Python properly.

## Roadmap

### v1: the lineup graph
- Async crawler that expands outward from seed DJs through shared lineups
- Relatedness that rewards b2b sets and recent shows, normalized so big headliners don't connect everyone
- "Who's closest to this DJ's world?" (personalized PageRank) and automatic scene detection

### v2: the sound graph
- Audio features and embeddings from legally sourced previews (BPM, key, style, vibe)
- Vector search for similar-sounding tracks, plus "find me *dark rolling techno with acid*"
- A hybrid recommender: sound similarity + set co-occurrence + lineup graph

## Starting seeds

San Francisco: Claudio PRC, DVS1, Lindsey Herbert, Fadi Mohem, Isabel Soto

## Development

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Data & ethics

wavelength only uses data sources whose terms allow it, respects rate limits and robots.txt, and stores audio *features*, never audio.
