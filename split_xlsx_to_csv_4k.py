from pathlib import Path

import pandas as pd


def split_xlsx_to_csv_chunks(xlsx_path: Path, output_dir: Path, rows_per_file: int) -> None:
    df = pd.read_excel(xlsx_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_rows = len(df)
    if total_rows == 0:
        print("No rows found. Nothing to split.")
        return

    for start in range(0, total_rows, rows_per_file):
        end = min(start + rows_per_file, total_rows)
        chunk = df.iloc[start:end]
        part_num = (start // rows_per_file) + 1
        output_file = output_dir / f"part_{part_num}.csv"
        chunk.to_csv(output_file, index=False)
        print(f"Saved: {output_file} (rows: {len(chunk)})")

    print(f"\nDone. Created {((total_rows - 1) // rows_per_file) + 1} file(s).")


if __name__ == "__main__":
    input_excel = "Routing Data for Sellrclub 20260107 (2).xlsx"
    output_directory = None  # Set to a folder name like "split_output" if you want a custom path.
    rows_per_file = 2000

    xlsx_path = Path(input_excel).expanduser().resolve()
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Input file not found: {xlsx_path}")

    output_dir = (
        Path(output_directory).expanduser().resolve()
        if output_directory
        else xlsx_path.parent / f"{xlsx_path.stem}_split"
    )

    split_xlsx_to_csv_chunks(xlsx_path, output_dir, rows_per_file)
