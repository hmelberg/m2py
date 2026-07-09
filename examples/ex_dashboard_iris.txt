#options.view = dashboard
#options.mode = python
#options.title = "Iris-dashboard"
#options.description = "Interaktiv demo av dashboard-visningen (#input, #%%, row=, wide)"
# load https://raw.githubusercontent.com/hmelberg/safestat/master/data/iris.csv as iris
import matplotlib.pyplot as plt

#input art = dropdown("setosa", "versicolor", "virginica")
#input min_lengde = slider(4, 8, step=1, default=4, label="Min. sepal-lengde")

#%% Fordeling, wide
sub = iris[(iris.species == art) & (iris.sepal_length >= min_lengde)]
sub.sepal_length.plot.hist(bins=12)
plt.title(art); plt.xlabel("sepal_length"); plt.show()

#%% Antall blomster, row=kpi
print(len(sub))

#%% Snitt sepal-lengde, row=kpi
print(round(sub.sepal_length.mean(), 2))

#%% Snitt sepal-bredde, row=kpi
print(round(sub.sepal_width.mean(), 2))
