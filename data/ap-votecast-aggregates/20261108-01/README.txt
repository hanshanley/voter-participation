Complete selected AP/NORC VoteCast participation aggregates, 2018/2020/2022/2024.
Not raw respondent data, administrative turnout, a linked panel or comparable fixed cohorts.
From the unpacked complete archive, without packages/network:
  python3 -m unittest discover -s tests -p test_ap_public_aggregates.py
  python3 -m scripts.ap_public_aggregates --inputs selected-aggregates.json --output reproduced
All permitted selected aggregate inputs, complete queries, withheld-query dispositions,
code and tests are included. Original microdata and private fine cells are excluded.
Read every source/frame/inference/support qualification in summary.json before use.
