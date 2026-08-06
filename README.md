# 0pi.es

**Interactive AI Governance. Zero Pies.**

> The internet's first AI governance gamification site. Probably. We didn't check.

Live at **[0pi.es](https://0pi.es)** · Chat at **[r/0pi](https://www.reddit.com/r/0pi/)**

Browser games for studying AI-governance and cloud-AI certifications — AIGP,
AWS AI Practitioner, Microsoft AI-901, EU and global AI legislation, and
vendor-neutral AI/ML concepts. **105 games, 2,101 scored cards.**

No cookies. No tracking. No pies.

## Boards, not quizzes

Sort a whole bank of cards into place, then score the board. Question-and-answer
drilling lives elsewhere; this is for the stuff that only sticks once you've had
to decide where something *belongs*.

- **Confident misses come back first.** Progress is per item. The cards you were
  sure about and still got wrong resurface soonest, because those are the ones
  that fail you.
- **Every reveal goes deeper.** Hand any board to Claude, ChatGPT or Perplexity —
  with what you missed, or the whole concept when you got it right.
- **Regulation that admits what changed.** Cards carry `asOf` and `status`. Where
  the law has moved since the textbooks — the Digital Omnibus deferring EU AI Act
  high-risk obligations, say — cards show what changed rather than silently
  correcting the source. The exam-correct answer and the current-law answer are
  not always the same, and pretending otherwise fails people.

## Run it yourself

Clone this and open anything in `gamification/` in a browser. Every page is a
single self-contained HTML file — card data is inlined, fonts are bundled — so
`file://` works: no server, no install, no build step, works on a plane.

There are no trackers or analytics anywhere, and the pages make no outbound
requests at all. Deep-link any game as `<lab>.html#g/<game-id>` — open a game
and copy the address bar.

This repo is the deployed site itself. The pages are generated artifacts of a
content pipeline that is not part of this repository, so treat the HTML as
read-only: hand-edits would be overwritten by the next content release.

## Contributing

Found something wrong or out of date? [Open an issue](https://github.com/0brains/0pies/issues)
or come argue about it at [r/0pi](https://www.reddit.com/r/0pi/). **Corrections
with a citation are the most useful thing you can send** — content fixes land
upstream and roll out here.

## Licence

[PolyForm Noncommercial 1.0.0](LICENSE). Use it, study from it, fork it, modify
it, share it — freely, for any noncommercial purpose. Personal study, hobby
projects, schools, universities, charities, public research and government use
are all explicitly permitted.

What you may not do is sell it: no reselling, no paid course or subscription
built on it, no bundling it into a commercial product.

That makes this *source-available*, not open source in the OSI sense — the OSI
definition doesn't allow restrictions on commercial use, and it seems better to
say so than to borrow the label. Want a commercial licence?
[Open an issue](https://github.com/0brains/0pies/issues).

Third-party material is **not** covered by that licence and stays under its
owners' terms — the AWS and Azure icon sets, vendor trademarks, and the world map
(CC BY-SA 3.0, share-alike). Read [NOTICE.md](NOTICE.md) before forking.

Not affiliated with or endorsed by the IAPP, Amazon, Microsoft, or any other
certification body. Independent study material, and not legal advice.
