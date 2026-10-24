import pandas as pd

# Cargar el CSV
df = pd.read_csv('scopus_export_otras.csv', encoding='utf-8-sig')

# Guardar como Excel
df.to_excel('scopus_export_otras.xlsx', index=False)