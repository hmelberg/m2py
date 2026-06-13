# translator.R — Main entry point for R → microdata.no translation.
#
# Usage:
#   result <- translate(r_code, df_name = "df")
#   cat(result$script)

# ── public API ────────────────────────────────────────────────────────────────

translate <- function(r_code, df_name = "df") {
  state  <- .new_state(df_name)
  blocks <- .split_blocks(r_code)

  for (blk in blocks) {
    if (blk$type == "microdata") {
      state <- .append(state, lines = blk$content)
    } else {
      state <- .translate_r_block(blk$content, state)
    }
  }

  list(
    script   = paste(state$lines,    collapse = "\n"),
    warnings = paste(state$warnings, collapse = "\n")
  )
}

# ── state ─────────────────────────────────────────────────────────────────────

.new_state <- function(df_name) {
  list(
    df_name    = df_name,
    current_df = NULL,
    known_dfs  = character(0),
    seed       = NULL,      # most recent set.seed() value, for `sample`
    lines      = character(0),
    warnings   = character(0)
  )
}

# Append the captured (or default) seed to a seedless `sample X` line — microdata
# requires `sample count|fraction seed`, and m2py rejects a seedless sample.
.inject_sample_seed <- function(result, state) {
  if (is.null(result) || is.null(result$lines)) return(result)
  needs <- grepl("^sample [^ ]+$", result$lines)
  if (!any(needs)) return(result)
  result$lines[needs] <- paste0(result$lines[needs], " ", state$seed %||% "1")
  if (is.null(state$seed))
    result$warnings <- c(result$warnings,
      "// sample: ingen set.seed() funnet — bruker seed=1; legg til set.seed() for reproduserbarhet")
  result
}

.append <- function(state, lines = NULL, warnings = NULL) {
  if (!is.null(lines)    && length(lines)    > 0) state$lines    <- c(state$lines,    lines)
  if (!is.null(warnings) && length(warnings) > 0) state$warnings <- c(state$warnings, warnings)
  state
}

# Emit "use <df_var>" when switching active dataset; updates current_df.
.ensure_active <- function(df_var, state) {
  # The initial active dataset is df_name (no `use` emitted yet), so treat a
  # NULL current_df as df_name — switching away from it must emit `use`.
  cur <- state$current_df %||% state$df_name
  if (!is.null(cur) && !is.null(df_var) && nzchar(df_var) && cur != df_var)
    state <- .append(state, lines = paste0("use ", df_var))
  state$current_df <- df_var
  state
}

.register_df <- function(name, state) {
  state$known_dfs <- unique(c(state$known_dfs, name))
  state
}

# Extract the dataset name from a data= argument, if it is a bare variable name.
.extract_data_arg <- function(args) {
  d <- args[["data"]]
  if (!is.null(d) && is.name(d)) as.character(d) else NULL
}

# ── block splitter ────────────────────────────────────────────────────────────

.split_blocks <- function(code) {
  raw_lines <- strsplit(code, "\n", fixed = TRUE)[[1]]
  blocks    <- list()
  cur_type  <- "r"
  cur_lines <- character(0)

  flush <- function() {
    if (length(cur_lines) > 0)
      blocks[[length(blocks) + 1L]] <<- list(
        type    = cur_type,
        content = paste(cur_lines, collapse = "\n")
      )
    cur_lines <<- character(0)
  }

  for (line in raw_lines) {
    s <- trimws(line)
    if      (grepl("^##\\s*microdata\\s*$", s, ignore.case = TRUE)) { flush(); cur_type <- "microdata" }
    else if (grepl("^##\\s*r\\s*$",         s, ignore.case = TRUE)) { flush(); cur_type <- "r" }
    else cur_lines <- c(cur_lines, line)
  }
  flush()

  if (length(blocks) == 0)
    blocks <- list(list(type = "r", content = code))
  blocks
}

# ── R block translation ───────────────────────────────────────────────────────

.translate_r_block <- function(r_code, state) {
  exprs <- tryCatch(
    parse(text = r_code, keep.source = FALSE),
    error = function(e) {
      state <<- .append(state, warnings = paste0("// Parse error: ", conditionMessage(e)))
      NULL
    }
  )
  if (is.null(exprs) || length(exprs) == 0) return(state)
  for (i in seq_along(exprs)) {
    # One statement that errors inside a handler must not abort the whole
    # translation — degrade it to a warning and continue with the rest.
    state <- tryCatch(
      .translate_stmt(exprs[[i]], state),
      error = function(e) .append(state, warnings = paste0(
        "// SKIPPED (translator error): ", deparse(exprs[[i]])[1],
        " — ", conditionMessage(e)))
    )
  }
  state
}

# ── statement dispatcher ──────────────────────────────────────────────────────

.translate_stmt <- function(expr, state) {
  if (!is.call(expr)) return(state)

  fn <- .callee_name(expr)

  if (fn %in% c("<-", "=", "->", "<<-"))
    return(.translate_assign(expr, state, fn))

  if (fn %in% c("|>", "%>%"))
    return(.translate_pipe_stmt(expr, NULL, state))

  if (fn %in% c("library", "require", "source", "setwd", "options",
                "install.packages"))
    return(state)

  # set.seed(N): capture the seed for a later `sample` (emits nothing itself)
  if (fn == "set.seed") {
    seed_args <- as.list(expr)[-1]
    sv <- if (length(seed_args) >= 1) translate_expr(seed_args[[1]], state$df_name) else NULL
    if (!is.null(sv)) state$seed <- sv
    return(state)
  }

  # ggplot2 chain: ggplot(...) + geom_*() + ...
  if (fn == "+" && .is_ggplot_chain(expr)) {
    result <- handle_ggplot_chain(expr, state$df_name)
    if (!is.null(result))
      return(.append(state, lines = result$lines, warnings = result$warnings))
  }

  # Standalone modelling / plot calls
  # Prefer data= arg for dataset context; fall back to current_df, then initial df_name.
  {
    sargs   <- as.list(expr)[-1]
    data_df <- .extract_data_arg(sargs)
    eff_df  <- data_df %||% state$current_df %||% state$df_name
    if (!is.null(data_df)) state <- .ensure_active(data_df, state)
    result  <- dispatch_standalone(fn, sargs, eff_df)
  }
  if (!is.null(result))
    return(.append(state, lines = result$lines, warnings = result$warnings))

  # Base-R data verbs used as a bare statement (no assignment)
  dz <- .desugar_base_verb(expr)
  if (!is.null(dz))
    return(.run_pipe_steps(NULL, dz$src, dz$steps, state))

  # Desugared native pipe used as a statement: summarise(group_by(df, g), ...)
  chain <- .unroll_dplyr(expr)
  if (!is.null(chain))
    return(.run_pipe_steps(NULL, chain$src, chain$steps, state))

  .append(state, warnings = paste0("// Untranslated: ", deparse(expr)))
}

# ── assignment ────────────────────────────────────────────────────────────────

.translate_assign <- function(expr, state, op) {
  if (op == "->") { lhs <- expr[[3]]; rhs <- expr[[2]] }
  else            { lhs <- expr[[2]]; rhs <- expr[[3]] }

  df_name <- state$df_name

  # df$col / df[["col"]] / df["col"]
  if (is.call(lhs)) {
    lhs_fn <- .callee_name(lhs)
    if (lhs_fn %in% c("$", "[[", "[")) {
      eff_df <- tryCatch(as.character(lhs[[2]]), error = function(e) NULL) %||% df_name
      col    <- col_from_node(lhs, eff_df)
      if (!is.null(col)) {
        state <- .ensure_active(eff_df, state)
        return(.translate_col_assign(col, rhs, eff_df, state))
      }
    }
  }

  if (is.name(lhs))
    return(.translate_df_assign(as.character(lhs), rhs, state))

  .append(state, warnings = paste0("// Unrecognised assignment: ", deparse(expr)))
}

# ── column assignment: df$col <- rhs ─────────────────────────────────────────

.translate_col_assign <- function(col, rhs, df_var, state) {
  fn    <- if (is.call(rhs)) .callee_name(rhs) else ""
  cargs <- if (is.call(rhs)) as.list(rhs)[-1] else list()

  if (fn %in% c("ifelse", "if_else")) {
    r <- .expand_ifelse(col, cargs, df_var)
    return(.append(state, lines = r$lines, warnings = r$warnings))
  }
  if (fn == "case_when") {
    r <- .expand_case_when(col, cargs, df_var)
    return(.append(state, lines = r$lines, warnings = r$warnings))
  }
  if (fn %in% c("recode", "dplyr::recode") && length(cargs) >= 1) {
    src <- col_from_node(cargs[[1]], df_var) %||%
           (if (is.name(cargs[[1]])) as.character(cargs[[1]]) else NULL)
    if (!is.null(src) && src == col) {
      r <- .expand_recode(col, cargs[-1], df_var)
      return(.append(state, lines = r$lines, warnings = r$warnings))
    }
  }

  # coalesce(x, fallback) → replace col = fallback if sysmiss(col)
  if (fn %in% c("coalesce", "dplyr::coalesce")) {
    r <- .expand_coalesce(col, cargs, df_var)
    return(.append(state, lines = r$lines, warnings = r$warnings))
  }

  # factor(x, levels=c(...), labels=c(...)) → define-labels + assign-labels
  if (fn == "factor") {
    r <- .expand_factor_labels(col, cargs, df_var)
    return(.append(state, lines = r$lines, warnings = r$warnings))
  }

  # as.numeric(col) / as.double(col) in-place → destring col
  if (fn %in% c("as.numeric", "as.double") && length(cargs) >= 1) {
    src <- col_from_node(cargs[[1]], df_var) %||%
           (if (is.name(cargs[[1]])) as.character(cargs[[1]]) else NULL)
    if (!is.null(src) && src == col)
      return(.append(state, lines = paste0("destring ", col)))
  }

  val <- translate_expr(rhs, df_var)
  if (!is.null(val))
    return(.append(state, lines = paste0("generate ", col, " = ", val)))

  .append(state, warnings = paste0("// Cannot translate: ",
                                   df_var, "$", col, " <- ", deparse(rhs)))
}

# ── dataframe assignment: df2 <- rhs ─────────────────────────────────────────

# Desugar a base-R data verb into its dplyr-pipe equivalent so it reuses the
# existing pipe machinery (clone-on-new-name, group_by, seed, joins).
# Returns list(src, steps) of synthetic dplyr call nodes, or NULL.
.desugar_base_verb <- function(expr) {
  fn   <- .callee_name(expr)
  args <- as.list(expr)[-1]
  .src_name <- function(node) if (is.name(node)) as.character(node) else NULL

  if (fn == "subset") {
    src  <- .src_name(args[["x"]] %||% (if (length(args) >= 1) args[[1]] else NULL))
    cond <- args[["subset"]] %||% (if (length(args) >= 2) args[[2]] else NULL)
    if (is.null(src) || is.null(cond)) return(NULL)
    steps <- list(as.call(list(as.name("filter"), cond)))
    sel <- args[["select"]] %||% (if (length(args) >= 3) args[[3]] else NULL)
    if (!is.null(sel)) steps <- c(steps, list(as.call(list(as.name("select"), sel))))
    return(list(src = src, steps = steps))
  }

  if (fn == "transform") {
    src <- .src_name(if (length(args) >= 1) args[[1]] else NULL)
    if (is.null(src)) return(NULL)
    mut_args <- args[-1]
    if (length(mut_args) == 0) return(NULL)
    return(list(src = src, steps = list(as.call(c(list(as.name("mutate")), mut_args)))))
  }

  if (fn == "aggregate") {
    f_node <- args[["formula"]] %||% (if (length(args) >= 1) args[[1]] else NULL)
    data_n <- .src_name(args[["data"]])
    fun_n  <- if (!is.null(args[["FUN"]])) .callee_name_or_name(args[["FUN"]]) else "mean"
    if (is.null(f_node) || !is.call(f_node) || .callee_name(f_node) != "~" || is.null(data_n))
      return(NULL)
    y <- if (is.name(f_node[[2]])) as.character(f_node[[2]]) else return(NULL)
    groups <- .formula_terms(f_node[[3]])
    gb  <- as.call(c(list(as.name("group_by")), lapply(groups, as.name)))
    agg <- as.call(c(list(as.name("summarise")),
                     setNames(list(as.call(list(as.name(fun_n), as.name(y)))), y)))
    return(list(src = data_n, steps = list(gb, agg)))
  }

  if (fn == "merge") {
    src <- .src_name(if (length(args) >= 1) args[[1]] else NULL)
    y   <- if (length(args) >= 2) args[[2]] else NULL
    if (is.null(src) || is.null(y)) return(NULL)
    join_args <- list(as.name("left_join"), y)
    if (!is.null(args[["by"]])) join_args <- c(join_args, list(by = args[["by"]]))
    return(list(src = src, steps = list(as.call(join_args))))
  }

  NULL
}

# Bare name of a function-valued argument: FUN = mean (a symbol) or FUN = "mean".
.callee_name_or_name <- function(node) {
  if (is.character(node)) return(node)
  if (is.name(node))      return(as.character(node))
  if (is.call(node))      return(.callee_name(node))
  "mean"
}

.translate_df_assign <- function(lhs_name, rhs, state) {
  df_name <- state$df_name

  # Simple copy: df2 <- df
  if (is.name(rhs)) {
    src <- as.character(rhs)
    if (src != lhs_name) {
      state <- .register_df(lhs_name, state)
      state <- .append(state, lines = paste0("clone-dataset ", src, " ", lhs_name))
    }
    return(state)
  }

  # Scalar literal → let binding  (e.g. YEAR <- 2020, label <- "text")
  if (is.numeric(rhs) || is.character(rhs) || is.logical(rhs)) {
    val <- translate_expr(rhs, df_name)
    if (!is.null(val))
      return(.append(state, lines = paste0("let ", lhs_name, " = ", val)))
    return(state)
  }
  if (!is.call(rhs)) return(state)
  rhs_fn <- .callee_name(rhs)

  # Magrittr or native pipe (only magrittr survives as |>/%%>%% in the AST)
  if (rhs_fn %in% c("|>", "%>%"))
    return(.translate_pipe_stmt(rhs, lhs_name, state))

  # Base-R bracket filter: df2 <- df[cond, ]
  if (rhs_fn == "[")
    return(.translate_bracket_filter(lhs_name, rhs, state))

  # Base-R data verbs (subset / transform / aggregate / merge) → dplyr pipe
  dz <- .desugar_base_verb(rhs)
  if (!is.null(dz))
    return(.run_pipe_steps(lhs_name, dz$src, dz$steps, state))

  # ggplot2 chain assigned: p <- ggplot(...) + geom_*()
  if (rhs_fn == "+" && .is_ggplot_chain(rhs)) {
    result <- handle_ggplot_chain(rhs, df_name)
    if (!is.null(result))
      return(.append(state, lines = result$lines, warnings = result$warnings))
  }

  # Modelling calls assigned: fit <- lm(y ~ x, data = df)
  # Prefer data= arg for dataset context; fall back to current_df, then initial df_name.
  {
    rhs_args <- as.list(rhs)[-1]
    data_df  <- .extract_data_arg(rhs_args)
    eff_df   <- data_df %||% state$current_df %||% df_name
    if (!is.null(data_df)) state <- .ensure_active(data_df, state)
    result   <- dispatch_standalone(rhs_fn, rhs_args, eff_df)
  }
  if (!is.null(result))
    return(.append(state, lines = result$lines, warnings = result$warnings))

  # KEY FIX: desugared native |> pipe → nested dplyr call
  # e.g. df <- df |> filter(...) |> mutate(...)
  #  becomes df <- mutate(filter(df, ...), ...)
  chain <- .unroll_dplyr(rhs)
  if (!is.null(chain))
    return(.run_pipe_steps(lhs_name, chain$src, chain$steps, state))

  .append(state, warnings = paste0("// Cannot translate assignment to ",
                                   lhs_name, ": ", deparse(rhs)))
}

# ── base-R bracket filter ─────────────────────────────────────────────────────

.translate_bracket_filter <- function(lhs_name, rhs, state) {
  rhs_args  <- as.list(rhs)[-1]
  src_node  <- rhs_args[[1]]
  src_df    <- if (is.name(src_node)) as.character(src_node) else state$df_name
  cond_node <- if (length(rhs_args) >= 2) rhs_args[[2]] else NULL

  if (src_df != lhs_name) {
    state <- .append(state, lines = c(paste0("clone-dataset ", src_df, " ", lhs_name),
                                      paste0("use ", lhs_name)))
    state <- .register_df(lhs_name, state)
    state$current_df <- lhs_name
  }

  if (!is.null(cond_node) && !is.name(cond_node)) {
    cond <- translate_expr(cond_node, src_df)
    if (!is.null(cond) && nzchar(cond))
      state <- .append(state, lines = paste0("keep if ", cond))
  }
  state
}

# ── unroll desugared native pipe ──────────────────────────────────────────────
#
# R 4.1+ desugars `x |> f(y)` at parse time into `f(x, y)`.
# So `df |> filter(a) |> mutate(b = e)` arrives as `mutate(filter(df, a), b = e)`.
# .unroll_dplyr() recovers list(src = "df", steps = [filter(a), mutate(b = e)])
# where each step has the data argument removed.

DPLYR_VERBS <- c(
  "filter", "mutate", "transmute", "select", "rename",
  "summarise", "summarize", "arrange", "drop_na", "distinct",
  "group_by", "ungroup", "slice", "slice_head", "slice_tail",
  "slice_max", "slice_min", "slice_sample",
  "count", "sample_n", "sample_frac",
  "pivot_longer", "pivot_wider",
  "left_join", "right_join", "inner_join", "full_join",
  "anti_join", "semi_join"
)

.unroll_dplyr <- function(expr) {
  fn_clean <- .callee_name(expr)
  if (!(fn_clean %in% DPLYR_VERBS)) return(NULL)

  all_args <- as.list(expr)[-1]          # named list of args
  if (length(all_args) == 0) return(NULL)

  # Find first *positional* (unnamed) argument — that is the data source
  nms <- names(all_args)
  if (is.null(nms)) nms <- rep("", length(all_args))
  first_pos_idx <- which(nms == "")[1]
  if (is.na(first_pos_idx)) return(NULL)

  data_arg  <- all_args[[first_pos_idx]]
  rest_args <- all_args[-first_pos_idx]

  # Rebuild verb call without the data argument
  verb_call <- as.call(c(list(expr[[1]]), rest_args))

  if (is.name(data_arg)) {
    # Base case: data source is a plain variable name
    return(list(src = as.character(data_arg), steps = list(verb_call)))
  }

  if (is.call(data_arg)) {
    inner_fn <- .callee_name(data_arg)
    if (inner_fn %in% DPLYR_VERBS) {
      inner <- .unroll_dplyr(data_arg)
      if (!is.null(inner))
        return(list(src = inner$src, steps = c(inner$steps, list(verb_call))))
    }
  }

  NULL
}

# ── pipe chain — flatten magrittr/native (when not yet desugared) ─────────────

.flatten_pipe <- function(expr) {
  fn <- .callee_name(expr)
  if (fn %in% c("|>", "%>%"))
    c(.flatten_pipe(expr[[2]]), list(expr[[3]]))
  else
    list(expr)
}

.translate_pipe_stmt <- function(pipe_expr, target_df, state) {
  steps  <- .flatten_pipe(pipe_expr)
  src    <- steps[[1]]
  verbs  <- steps[-1]
  src_df <- if (is.name(src)) as.character(src) else NULL
  .run_pipe_steps(target_df, src_df, verbs, state)
}

# ── core pipe step runner ─────────────────────────────────────────────────────
# Used for both magrittr pipes and unrolled native pipes.
# `steps`: list of verb calls, each WITHOUT the data argument.

.run_pipe_steps <- function(target_df, src_df, steps, state) {
  eff_df <- src_df %||% state$df_name

  # Clone if assigning to a new name
  if (!is.null(target_df) && !is.null(src_df) && target_df != src_df) {
    state <- .append(state, lines = c(paste0("clone-dataset ", src_df, " ", target_df),
                                      paste0("use ", target_df)))
    state <- .register_df(target_df, state)
    state$current_df <- target_df
    eff_df <- target_df  # subsequent steps operate on the clone, not the source
  } else if (!is.null(src_df)) {
    state <- .ensure_active(src_df, state)
  }

  group_by_str <- NULL

  for (step in steps) {
    if (!is.call(step)) next
    fn_clean <- .callee_name(step)
    sargs    <- as.list(step)[-1]

    if (fn_clean == "group_by") {
      group_by_str <- paste(sapply(sargs, function(a) {
        if (is.name(a)) as.character(a) else deparse(a)
      }), collapse = " ")
      next
    }
    if (fn_clean == "ungroup") { group_by_str <- NULL; next }

    result <- dispatch_dplyr(fn_clean, sargs, eff_df, group_by_str)
    result <- .inject_sample_seed(result, state)

    if (!is.null(result)) {
      state <- .append(state, lines = result$lines, warnings = result$warnings)
    } else {
      result2 <- dispatch_standalone(fn_clean, sargs, eff_df)
      if (!is.null(result2))
        state <- .append(state, lines = result2$lines, warnings = result2$warnings)
      else
        state <- .append(state, warnings = paste0("// Untranslated step: ", deparse(step)))
    }
  }

  if (!is.null(target_df)) state$current_df <- target_df
  state
}

# Expanders (.expand_ifelse / .expand_case_when / .expand_recode) live in
# expanders.R — the single shared source used by both commands.R and this file.
