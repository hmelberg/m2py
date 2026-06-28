# expanders.R — shared expansion of dplyr/base constructs that map to several
# microdata commands (generate + replace ... if). Single source of truth: these
# used to be duplicated in commands.R and translator.R (with the copies silently
# diverging — the case_when priority bug lived in one of them). Sourced after
# expr.R (needs translate_expr / .callee_name) and before commands.R/translator.R.

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
  # dplyr case_when is FIRST-match-wins. Sequential `replace` overwrites, so the
  # non-default branches must be emitted in REVERSE source order (then the
  # earliest-listed condition is applied last and wins). The TRUE ~ default is
  # applied last via sysmiss so it only fills rows no branch matched.
  warns        <- character(0)
  non_default  <- character(0)   # replace lines, source order
  default_line <- NULL
  for (cw in cargs) {
    if (!is.call(cw) || .callee_name(cw) != "~") next
    cond_node <- cw[[2]]
    val_node  <- cw[[3]]
    val <- translate_expr(val_node, df_name)
    if (is.null(val)) {
      warns <- c(warns, paste0("// case_when: untranslatable value for ", col)); next
    }
    is_default <- (is.name(cond_node) && as.character(cond_node) %in% c("TRUE", "T")) ||
                  (is.logical(cond_node) && isTRUE(cond_node))
    if (is_default) {
      default_line <- paste0("replace ", col, " = ", val, " if sysmiss(", col, ")")
    } else {
      cond <- translate_expr(cond_node, df_name)
      if (!is.null(cond))
        non_default <- c(non_default, paste0("replace ", col, " = ", val, " if ", cond))
      else
        warns <- c(warns, paste0("// case_when: untranslatable condition for ", col))
    }
  }
  lines <- c(paste0("generate ", col, " = ."), rev(non_default), default_line)
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

# case_match(src, v1 ~ r1, c(v2,v3) ~ r2, .default = d) — value matching.
# Each row's src matches at most one arm, so order is irrelevant (no reverse).
.expand_case_match <- function(col, cargs, df_name) {
  if (length(cargs) < 2)
    return(list(lines = character(0), warnings = paste0("// case_match: too few args for ", col)))
  src <- translate_expr(cargs[[1]], df_name)
  if (is.null(src))
    return(list(lines = character(0), warnings = paste0("// case_match: untranslatable source for ", col)))
  warns <- character(0)
  lines <- paste0("generate ", col, " = .")
  nms <- names(cargs) %||% rep("", length(cargs))
  for (i in 2:length(cargs)) {
    if (nms[i] == ".default") next   # handled after the loop
    arm <- cargs[[i]]
    if (!is.call(arm) || .callee_name(arm) != "~") next
    res <- translate_expr(arm[[3]], df_name)
    if (is.null(res)) { warns <- c(warns, paste0("// case_match: untranslatable result for ", col)); next }
    val_node <- arm[[2]]
    if (is.call(val_node) && .callee_name(val_node) == "c") {
      vals <- sapply(as.list(val_node)[-1], translate_expr, df_name = df_name)
      if (any(sapply(vals, is.null))) { warns <- c(warns, paste0("// case_match: untranslatable values for ", col)); next }
      cond <- paste0("inlist(", src, ", ", paste(unlist(vals), collapse = ", "), ")")
    } else {
      v <- translate_expr(val_node, df_name)
      if (is.null(v)) { warns <- c(warns, paste0("// case_match: untranslatable value for ", col)); next }
      cond <- paste0(src, " == ", v)
    }
    lines <- c(lines, paste0("replace ", col, " = ", res, " if ", cond))
  }
  if (".default" %in% nms) {
    dv <- translate_expr(cargs[[".default"]], df_name)
    if (!is.null(dv)) lines <- c(lines, paste0("replace ", col, " = ", dv, " if sysmiss(", col, ")"))
  }
  list(lines = lines, warnings = warns)
}

# Column names from an across() column spec: c(a, b) or a bare name.
.across_cols <- function(node) {
  if (is.call(node) && .callee_name(node) == "c")
    return(unlist(lapply(as.list(node)[-1], function(a)
      if (is.name(a)) as.character(a) else if (is.character(a)) a else NULL)))
  if (is.name(node)) return(as.character(node))
  NULL
}

# Replace the across lambda placeholder (.x / .) with a column symbol.
.subst_placeholder <- function(node, col) {
  if (is.name(node)) {
    if (as.character(node) %in% c(".x", ".")) return(as.name(col))
    return(node)
  }
  if (is.call(node)) {
    for (i in seq_along(node)) node[[i]] <- .subst_placeholder(node[[i]], col)
    return(node)
  }
  node
}

# across(cols, ~ .x * 2) in mutate → one `generate col = expr` per column.
.expand_across_mutate <- function(cargs, df_name) {
  if (length(cargs) < 2)
    return(list(lines = character(0), warnings = "// across: needs columns and a function"))
  cols <- .across_cols(cargs[[1]])
  fn_node <- cargs[[2]]
  if (is.null(cols) || !is.call(fn_node) || .callee_name(fn_node) != "~")
    return(list(lines = character(0), warnings = "// across: only the ~ lambda form is supported in mutate"))
  body <- fn_node[[2]]
  lines <- character(0); warns <- character(0)
  for (col in cols) {
    val <- translate_expr(.subst_placeholder(body, col), df_name)
    if (!is.null(val)) lines <- c(lines, paste0("generate ", col, " = ", val))
    else warns <- c(warns, paste0("// across: cannot translate for ", col))
  }
  list(lines = lines, warnings = warns)
}

# across(cols, mean) in summarise → one "(stat) col -> col" spec per column.
.expand_across_summarise <- function(cargs, df_name) {
  if (length(cargs) < 2)
    return(list(specs = character(0), warnings = "// across: needs columns and a function"))
  cols <- .across_cols(cargs[[1]])
  fn   <- .callee_name_or_name(cargs[[2]])
  stat <- AGG_STAT_MAP[[fn]]
  if (is.null(cols) || is.null(stat))
    return(list(specs = character(0),
                warnings = paste0("// across: unsupported function '", fn, "' in summarise")))
  list(specs = paste0("(", stat, ") ", cols, " -> ", cols), warnings = character(0))
}
