#options.view = dashboard
#options.mode = r
#options.title = "Arbeidsforhold (mockdata)"
#options.description = "DuckDB monterer parquet-dataene, R visualiserer - helt uten Python-runtime"
# connect https://raw.githubusercontent.com/hmelberg/safestat/master/static_data/jobb.parquet as kilde, kind(parquet)
# load kilde as jobb

#input startaar = slider(2015, 2023, step=1, default=2018, label="Fra startaar")
#input min_pst = slider(5, 100, step=5, default=50, label="Min. stillingsprosent")

#%% Stillingsprosent-fordeling, wide
sub <- jobb[which(jobb$ARBLONN_ARB_START >= startaar * 100 & jobb$ARBLONN_ARB_STILLINGSPST >= min_pst), ]
hist(sub$ARBLONN_ARB_STILLINGSPST, breaks = 20, col = "steelblue",
     main = "", xlab = "Stillingsprosent", ylab = "Antall")

#%% Arbeidsforhold, row=kpi
cat(nrow(sub))

#%% Andel heltid, row=kpi
cat(round(100 * mean(sub$ARBLONN_ARB_STILLINGSPST == 100), 1), "%")

#%% Personer, row=kpi
cat(length(unique(sub$ARBEIDSFORHOLD_PERSON)))

#%% Ansettelsesform, tab=Detaljer
barplot(table(sub$ARBLONN_ARB_ANSETTELSESFORM), col = "steelblue",
        xlab = "Ansettelsesform (kode)", ylab = "Antall")

#%% Startaar, tab=Detaljer
barplot(table(substr(sub$ARBLONN_ARB_START, 1, 4)), col = "steelblue", ylab = "Antall")
