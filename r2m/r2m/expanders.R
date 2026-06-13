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
