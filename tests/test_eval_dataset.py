import csv
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


class EvaluationDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).parent.parent
        self.datasets_root = root / "eval" / "phoenix" / "datasets"

    def _assert_dataset_sync(self, dataset_name: str, expected_count: int) -> None:
        dataset_dir = self.datasets_root / dataset_name
        tree = ET.parse(dataset_dir / "evaluation.xml")
        pairs = tree.getroot().findall("qa_pair")
        self.assertEqual(len(pairs), expected_count)
        for pair in pairs:
            self.assertTrue((pair.findtext("question") or "").strip())
            self.assertTrue((pair.findtext("answer") or "").strip())

        xml_rows = [
            (
                (pair.findtext("question") or "").strip(),
                (pair.findtext("answer") or "").strip(),
            )
            for pair in pairs
        ]
        csv_path = dataset_dir / "examples" / f"{dataset_name}.csv"
        with csv_path.open(encoding="utf-8", newline="") as handle:
            csv_rows = [
                (row["query"].strip(), row["responses"].strip())
                for row in csv.DictReader(handle)
            ]

        self.assertEqual(csv_rows, xml_rows)

    def test_legacy_dataset_remains_synchronized(self) -> None:
        self._assert_dataset_sync("veteran-access-eval-0", 10)

    def test_m63_dataset_contains_twelve_synchronized_pairs(self) -> None:
        self._assert_dataset_sync("veteran-access-eval-1", 12)


if __name__ == "__main__":
    unittest.main()
