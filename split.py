import pandas as pd
import numpy as np
import os

def split_excel_into_parts(input_file, output_folder, num_files=4):
    # Read the Excel file
    df = pd.read_excel(input_file)



    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Split dataframe into num_files parts (handles leftover rows automatically)
    split_dfs = np.array_split(df, num_files)

    # Save each part into a separate Excel file
    for i, split_df in enumerate(split_dfs):
        output_file = os.path.join(output_folder, f"split_part_{i+1}.xlsx")
        split_df.to_excel(output_file, index=False)

        print(f"Saved: {output_file}  (rows: {len(split_df)})")

    print("\n✅ Done! All rows were included and no data was skipped.")


# -------------------------------
# Example Usage
# -------------------------------
input_excel = "Odoo Customer Clean parser.xlsx"      # <-- replace with your file name
output_directory = "split_folders_odoo_customers"      # <-- replace with your folder name

split_excel_into_parts(input_excel, output_directory, num_files=4)
