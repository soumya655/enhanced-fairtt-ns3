# Paper reference plot data

`paper_reference_values.csv` contains the numeric series formerly written
directly inside `scripts/generate_paper_exact_plots.py`. The migration
preserves those values unchanged; the plotter reads them from this CSV.

These are legacy reference values, not output from the current ns-3
simulation. Their location under `results/TcpBbr` does not make them current
simulation output; the paper-style plots carry a provenance note. For plots of
current simulation runs, use `scripts/modified_plot_results.py` or
`scripts/generate_paper_plots.py`, which read generated run CSVs.

Regenerate the reference figures with:

```bash
python3 scripts/generate_paper_exact_plots.py
```
