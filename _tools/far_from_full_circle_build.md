# Far from Full Circle: build reference

How the built page works, for chats that change a component. The code is the source of truth for sizes, colors, timings, label placement and every word on the page; this file records the intent and rules behind it. What each chart means and what is left to build live in the brief (`posts/far-from-full-circle-brief.md` in the claude.ai project).

## Stack

Plain HTML and SVG, D3 7.9.0 from jsDelivr, `position: sticky` for pinning, Newsreader self-hosted. Beats start by the transition timing rule below, by the page's own scroll check (Scrollama removed November 19).

## Files

In `projects/far_from_full_circle/`: the page `a_circularity_story.html`; the data file `far_from_full_circle_data.js`; the font; `far_from_full_circle_shards.js`, the ring's solver for the game and explorers (usage at the top of the file; `useLess` takes one share for every material or one per material; `reshape` takes out named shards and resizes the rest to exact shares).

The data file's blocks are `build_data.py`'s (`game` and `imports` included), merged in with the file's own blocks kept: `examples`, `center_shards` (the full disc, panel 4's `recycle`, panel 5's `less`, panel 6's `both` with its `rec` disc after recycling 70% and its final disc) and `food_heaps`. It carries `replacement`, and each country's figures at that replacement: `extra_recycled_70pct_kt`, `rate_70pct_recycled`, `rate_70pct_recycled_if_adding`, `replaced_70pct_recycled`, `gone_without_70pct_recycled`, `recycled_share_to_close`, `less_new_material_to_close`, `not_recycled_mix` and `waste_check`, plus 20b's `highlights` and `climate_total_mt`.

## Layout

- One build, phone first: a pinned square chart with text cards scrolling over it, pinned in bursts. Cards aim for up to 7 lines, about 270 characters on a phone.
- Wide screens start at 800 px (`min-width: 800px`): the same build in two columns, chart left, cards right. The chart takes the smallest of about 55% of the width, the viewport's height less a top and bottom margin, and 560 px; cards take a 360 to 420 px column. The explorers and the game use the same arrangement. The hero's first card is in place at load, level with the ring, so the title is above the fold.
- Nav: no bar and no menu, at every width. The home icon sits at the page's top left and scrolls away; `--nav` is 0. On a phone the icon covers the hero chart's top left (about 37 units square of the 400-unit grid): keep text out of it in panel 1.
- Transition timing: each beat's transition starts as soon as the previous card is almost clear of the top edge, or, when the beat brings a new chart, as soon as that chart is 90% visible. Transitions are timed, not tied to scroll position, each tuned on a real phone to end around when the card reaches its place at a normal scroll speed (right below the chart on a phone, centered on wide screens). Start around 600 to 900 ms; on a phone the stretch from start to place is about 170 px of scrolling. On wide screens a beat starts once its card is 260 px of scrolling from its place (a chart's first card also waits for the chart to be 75% visible), and every forward beat plays 260/170 times as long. Scrolling back quickly animates to the earlier beat's state. Reduced motion speeds up each animation to its end state.
- Optional parts (20a, 20b, the game) sit inline as standalone figures, not pinned, each with a skip-ahead link.
- The closer is unpinned paragraphs with no chart: a white band the full width of the page, with the text in a centered column of at most 720 px, in the cards' type, its section title on top and its "Sources and notes" link at the end. It has no cards, so it doesn't count as a step.
- The credit line closes the closer, after its "Sources and notes" link: a hairline, then "Created by Milcah M. Joseph" and links to Portfolio, GitHub and LinkedIn, centered in 15 px secondary ink. GitHub and LinkedIn open in a new tab.
- Sections: each new kind of chart starts a section with a takeaway title, above the chart on a phone and at the top of the first card on wide screens. The ring's title is the hero's; the explorers share one title above the country picker; the game's tops its text column; the closer's tops its paragraphs.
- Notes: no collapsibles. Each section ends with a "Sources and notes" link (in its last card; in the explorers and the game, under the text or chart; in the closer, after its last paragraph) to its subsection of the one Sources and notes section at the end, which opens with Method, then a subsection per section headed by its title, each with a back link. Before it, after the closer, a floor band shows the terrazzo unfaded (fading in and out over its top and bottom 22vh), with one white card in the middle: a line linking the analysis repo, then the "About the drawings" note.
- Annotations sit inside the chart's own box, never as floating tooltips.
- Each card declares the chart's whole state, so scrolling back, resizing and reduced motion all work.
- One card per item in the sequence (panel 4 has three, panels 5 and 6 two). An idea is never split across several small cards.
- Caveats appear on the charts as well as in the notes: the 2024 estimate, the factory gate, recycling held fixed when material is cut, the assumed replacement. Panel 20's not like for like is in its card and notes only.
- Mobile toolbars: anything sized or triggered by viewport height uses `svh` or a pixel value that changes only with the width, never a value read on every resize. Anything that pins or scrolls to a position subtracts `--nav`.

## Chart mechanics

- Ring: past 24% (20a, the game), the arc runs into a thicker translucent second lap. Panel 3 marks the share that comes back as waste; panel 4 fades the gold and adds a striped stretch until the ring closes while shards of the replaced materials fly off, then the disc closes up; panel 5 restores the full disc, removes shards (the same share of every material) and shrinks the disc; panel 6 restores the full disc and plays 20a's route for the EU, its highlight shown from the beat's start. Shards taken out fly off to the right, over the cards on wide screens (20a's and the game's over their text). A key under the ring builds by panel.
- Waterfall: net arrows only on highlighted steps (8, 9, 11 and 20b's), which dim the rest, drawn after the step's bars.
- ZIN: both towers start brown, then ZIN's top floors clear to daylight from the roof down to 377.
- Ribbon: panels 16 and 17 fade the other materials.
- Panel 20: IKEA's estimated tonnes hatched; only the per-tonne lines under the chart, the caveats in the card.

## Explorers (20a, 20b)

- Each has its own dropdown (every EU country), unsynchronized; 20b offers a small link to show the country picked in 20a. Each animates when it enters view and when the country changes; reduced motion shows the end state.
- 20a: above the ring, "[x]% less new material" over the split; a split wider than 260 units wraps after its semicolon, and the ring and keys sit 12 units lower than panel 1's to fit three lines. The country's ring at its 2022 rate, then both levers at once, as one beat: recycling rises to 70% of treated waste (or holds at the country's own share if higher) while every shard that goes flies off in one scattered run, both those recycling replaces (by `not_recycled_mix`) and the cut still needed (the same share of every material); then the disc closes up until the ring closes. The `rec` disc is only the solver's step to the last one, never drawn. Countries past 24% after recycling lose no further shards and run into the second lap. Every disc starts at the same size, meaning 100% of that country's new material use. Its key is drawn at 0.82 of the pinned rings' size.
- 20b: axis "Change in circularity rate since 2010", fitted to each country's range but never spanning less than panel 7's 4.8; the axis is the same length for every country. Up to two highlighted steps per country (Romania none), each labeled with the rate's two ends and the arrow that carries the story, with a net arrow; other steps dim. Labels sit in a two-row band between the axis title and the bars, reserved for every country, highlights or not. Each label sits beside its leader, right or left, in the lower row unless two labels need both; no label overlaps another or crosses a leader. Highlights are set in `build_data.py` (`WATERFALL_HIGHLIGHTS`) and written to the data file's `highlights`, so Eurostat's update means a rebuild. The "2022 to 2024: Eurostat's estimate" caveat sits above the source line, shown only while the last step is estimated. Cards are hand-written per country in the page's `XW_TEXT`.

## The ring game (panel 21)

- First beat: the card holds the instructions and a Start button, with two curly arrows on the chart, to the knob and to the keys. Start, or the reader's first move, replaces them with the numbers, keeping the chart where it is on screen; "Start again" doesn't bring them back.
- Recycling knob at the arc's tip, in the arc's colors, dragged around the ring (arrow keys 1% of waste, Page Up and Down 10%). It sets the share of treated waste recycled, from 2022's 41% to 100% in whole percents, to whichever share puts the tip nearest the pointer, and follows the drag into the second lap (up to one full lap). The disc re-solves on release; the arc and numbers follow live.
- Taps: each removes 5.5% of 2022's new material from that material, as whole shards. The tap that would pass 24% stops exactly at 24%. Recycling replaces first and taps cut only what it hasn't replaced, so a partial cut gives way as recycling rises; a material tapped to nothing stays gone. Keys show "−xx%" and grey out at −100%. "Start again" resets.
- Numbers, no scales: under the keys on a phone, in the card column on wide screens. Above the ring, as in 20a: "[x]% less new material" over the split ("recycling held at its 2022 level" when recycling isn't raised). The multiple of 2022's recycling shows only here, two decimals below 1.1x, never "recycling rate", with the EEA's 70% for 2030 and 90% for 2050 under it.
- Ending: when the ends meet and the disc settles, the arc swells and a thin gold ripple spreads and fades (not under reduced motion), again each time the ring closes after dropping below 24%. It shows above the numbers on wide screens and after them on a phone. Its comparison is heaviest first at the same recycling and weight as the reader's route.
- Each tap or release re-solves with `reshape` in a Web Worker (on the page where no worker starts); leaving shards fly off as in panel 5, then the new layout blends in. Solves take under 0.1 s on a laptop. `FFC.game` plays it by script.

## Look

Colors live only in the page's CSS, as variables named by role.

- Page: light, white base, a terrazzo print that scrolls with the page (one seamless 1600-unit tile, drawn 900 px on a phone and 1280 px on wide screens, anchored to the page's top left) behind a mask fixed to the screen. On a phone it fades to almost nothing behind the pinned chart and is clear below it; on wide screens it is clear in the side margins and fades to almost nothing across the chart and cards. Nothing in the background darker than relative luminance 0.82.
- Roles: blues for material used, one per material (minerals EU blue, metal ores sky, fossil fuels azure, biomass cobalt); lighter gold for what comes back; deep gold for the 24% target; light gold for waste that could come back; a darker deep gold for the second lap. Building and object tones (ZIN, the balance, the food) are not series colors. Controls have their own variables; the knob keeps the arc's colors.
- Text: ink and secondary, never in a series color, never on the shards. White on EU blue and cobalt, ink on gold.
- Highlights in the closer: `mark`, a band of `--highlight` (the lighter gold at 40% on white) under the lower part of the line, ink text (13.3:1). Not a series color.
- Flat fills, no outlines or shadows, square white cards with no outline. Rounded ends only on the ring's arc, pointed ends only on the waterfall's bars; hatching only for estimates and recycling added in a scenario. Page text never names the hatching.
- Labels that pair up line up, such as a name level with the midpoint of its two shares.
- Type: Newsreader with its optical sizes; no sans serifs. Card text (cards, the explorers' and game's text, the closer) is 18 px on a phone and 20 px on wide screens. Chart text scales with the chart, except on wide screens, where it is capped at 1.075 px per viewBox unit (`--cf`, set once at load), so labels stay smaller than the card text.

## Checking

- `check_page.py` opens the page as a file (font blocked, 20a and the game solving on the page, so mid-flight states are expected). `check_steps.py` serves the page and checks it card by card, each scrolled to its place, with reduced motion; its screenshot can catch panel 6's beat mid-way. `check_numbers.py` lists the page's numbers that no repo table matches, checking each country's text (20a's warning lines, 20b's cards) against that country's rows only, and lists apart those found only in `research.md`. A match can be a coincidence: it shows a number has a source, not that it's the right one. Usage at the top of each file.
- None steps through the explorers' countries or plays the game: render each separately when its charts change (the game through `FFC.game`, the ring's states through `FFC.draw.ring`). Check transitions separately.
- If the weight shares, the replacement, or the EU's 2022 circular use or consumption change, rerun `make_shards.py` (`--check` re-measures) and check all five discs by eye (full, panel 4's, panel 5's and panel 6's last; its `rec` disc isn't drawn). After any change to `make_heaps.py`, check its printout (42.2% exactly) and `--preview`.
