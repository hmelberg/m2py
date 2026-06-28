# r_equiv_helper.R — ground truth + translation for the r2m equivalence harness.
#
# Usage:
#   Rscript r_equiv_helper.R <r2m_dir> <input_csv> <snippet_file> <result_var> <out_result_csv>
#
# Runs the R snippet against the input data (ground truth) and writes the
# resulting `result_var` data frame to <out_result_csv>; prints the r2m
# translation of the snippet to stdout. Used by tests/test_equivalence.py.

args <- commandArgs(trailingOnly = TRUE)
r2m_dir        <- args[1]
input_csv      <- args[2]
snippet_file   <- args[3]
result_var     <- args[4]
out_result_csv <- args[5]

for (f in c("expr.R", "expanders.R", "commands.R", "translator.R"))
  source(file.path(r2m_dir, f))

snippet <- paste(readLines(snippet_file, warn = FALSE), collapse = "\n")

# ── ground truth: run the snippet in base R ──
df  <- read.csv(input_csv, stringsAsFactors = FALSE)
env <- new.env()
assign("df", df, envir = env)
eval(parse(text = snippet), envir = env)
res <- get(result_var, envir = env)
write.csv(res, out_result_csv, row.names = FALSE)

# ── translation: emit the microdata script on stdout ──
cat(translate(snippet)$script)
