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
    lines      = character(0),
    warnings   = character(0)
  )
}

.append <- function(state, lines = NULL, warnings = NULL) {
  if (!is.null(lines)    && length(lines)    > 0) state$lines    <- c(state$lines,    lines)
  if (!is.null(warnings) && length(warnings) > 0) state$warnings <- c(state$warnings, warnings)
  state
}

# Emit "use <df_var>" when switching active dataset; updates current_df.
.ensure_active <- function(df_var, state) {
  if (!is.null(state$current_df) && !is.null(df_var) &&
      nzchar(df_var) && state$current_df != df_var)
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
  for (i in seq_along(exprs)) state <- .translate_stmt(exprs[[i]], state)
  state
}

# ── statement dispatcher ──────────────────────────────────────────────────────

.translate_stmt <- function(expr, state) {
  if (!is.call(expr)) return(state)

  fn <- tryCatch(as.character(expr[[1]]), error = function(e) "")

  if (fn %in% c("<-", "=", "->", "<<-"))
    return(.translate_assign(expr, state, fn))

  if (fn %in% c("|>", "%>%"))
    return(.translate_pipe_stmt(expr, NULL, state))

  if (fn %in% c("library", "require", "source", "setwd", "options",
                "install.packages"))
    return(state)

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
    lhs_fn <- tryCatch(as.character(lhs[[1]]), error = function(e) "")
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
  fn    <- if (is.call(rhs)) tryCatch(as.character(rhs[[1]]), error = function(e) "") else ""
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

.translate_df_assign <- function(lhs_name, rhs, state) {
  df_name <- state$df_name

  # Simple copy: df2 <- df
  if (is.name(rhs)) {
    src <- as.character(rhs)
    if (src != lhs_name) {
      state <- .register_df(lhs_name, state)
      state <- .append(state, lines = paste0("clone-dataset ", lhs_name))
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
  rhs_fn <- tryCatch(as.character(rhs[[1]]), error = function(e) "")

  # Magrittr or native pipe (only magrittr survives as |>/%%>%% in the AST)
  if (rhs_fn %in% c("|>", "%>%"))
    return(.translate_pipe_stmt(rhs, lhs_name, state))

  # Base-R bracket filter: df2 <- df[cond, ]
  if (rhs_fn == "[")
    return(.translate_bracket_filter(lhs_name, rhs, state))

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
    state <- .append(state, lines = c(paste0("clone-dataset ", lhs_name),
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
  fn_clean <- tryCatch(sub("^.*::", "", as.character(expr[[1]])), error = function(e) "")
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
    inner_fn <- tryCatch(sub("^.*::", "", as.character(data_arg[[1]])), error = function(e) "")
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
  fn <- tryCatch(as.character(expr[[1]]), error = function(e) "")
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
    state <- .append(state, lines = c(paste0("clone-dataset ", target_df),
                                      paste0("use ", target_df)))
    state <- .register_df(target_df, state)
    state$current_df <- target_df
  } else if (!is.null(src_df)) {
    state <- .ensure_active(src_df, state)
  }

  group_by_str <- NULL

  for (step in steps) {
    if (!is.call(step)) next
    fn_raw   <- tryCatch(as.character(step[[1]]), error = function(e) "")
    fn_clean <- sub("^.*::", "", fn_raw)
    sargs    <- as.list(step)[-1]

    if (fn_clean == "group_by") {
      group_by_str <- paste(sapply(sargs, function(a) {
        if (is.name(a)) as.character(a) else deparse(a)
      }), collapse = " ")
      next
    }
    if (fn_clean == "ungroup") { group_by_str <- NULL; next }

    result <- dispatch_dplyr(fn_clean, sargs, eff_df, group_by_str)

    if (!is.null(result)) {
      state <- .append(state, lines = result$lines, warnings = result$warnings)
    } else {
      result2 <- dispatch_standalone(fn_raw, sargs, eff_df)
      if (!is.null(result2))
        state <- .append(state, lines = result2$lines, warnings = result2$warnings)
      else
        state <- .append(state, warnings = paste0("// Untranslated step: ", deparse(step)))
    }
  }

  if (!is.null(target_df)) state$current_df <- target_df
  state
}

# ── expanders (ifelse / case_when / recode) ───────────────────────────────────

.expand_ifelse <- function(col, cargs, df_name) {
  if (length(cargs) < 3)
    return(list(lines = character(0),
                warnings = paste0("// ifelse: too few args for ", col)))
  cond <- translate_expr(cargs[[1]], df_name)
  tval <- translate_expr(cargs[[2]], df_name)
  fval <- translate_expr(cargs[[3]], df_name)
  if (is.null(cond) || is.null(tval) || is.null(fval))
    return(list(lines = character(0),
                warnings = paste0("// ifelse: untranslatable expression for ", col)))
  list(
    lines    = c(paste0("generate ", col, " = ", fval),
                 paste0("replace ",  col, " = ", tval, " if ", cond)),
    warnings = character(0)
  )
}

.expand_case_when <- function(col, cargs, df_name) {
  lines <- paste0("generate ", col, " = .")
  warns <- character(0)
  for (cw in cargs) {
    if (!is.call(cw) ||
        tryCatch(as.character(cw[[1]]), error = function(e) "") != "~") next
    cond_node <- cw[[2]]
    val_node  <- cw[[3]]
    val <- translate_expr(val_node, df_name)
    if (is.null(val)) {
      warns <- c(warns, paste0("// case_when: untranslatable value for ", col)); next
    }
    is_default <- (is.name(cond_node) && as.character(cond_node) %in% c("TRUE", "T")) ||
                  (is.logical(cond_node) && isTRUE(cond_node))
    if (is_default) {
      lines <- c(lines, paste0("replace ", col, " = ", val, " if sysmiss(", col, ")"))
    } else {
      cond <- translate_expr(cond_node, df_name)
      if (!is.null(cond))
        lines <- c(lines, paste0("replace ", col, " = ", val, " if ", cond))
      else
        warns <- c(warns, paste0("// case_when: untranslatable condition for ", col))
    }
  }
  list(lines = lines, warnings = warns)
}

.expand_recode <- function(col, pairs, df_name) {
  nms <- names(pairs)
  if (is.null(nms) || !any(nzchar(nms)))
    return(list(lines = character(0),
                warnings = paste0("// recode: no named pairs for ", col)))
  pair_strs <- character(0)
  for (j in seq_along(pairs)) {
    if (!nzchar(nms[j])) next
    val <- translate_expr(pairs[[j]], df_name)
    if (is.null(val))
      return(list(lines = character(0),
                  warnings = paste0("// recode: untranslatable value for ", col)))
    pair_strs <- c(pair_strs, paste0("(", nms[j], "=", val, ")"))
  }
  list(lines = paste0("recode ", col, " ", paste(pair_strs, collapse = " ")),
       warnings = character(0))
}
