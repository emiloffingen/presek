from unittest.mock import MagicMock, patch

from tasks.maintenance import repair_cluster_representative_image


def test_repair_cluster_representative_image_replaces_weak_logo():
    client = MagicMock()
    with (
        patch("tasks.maintenance.db") as mock_db,
        patch("tasks.maintenance.image_url_reachable", return_value=True),
    ):
        mock_db.execute.return_value = [
            {"image_url": "https://cdn.example.com/uploads/hero-1200x900.jpg", "source": "SDK"},
        ]

        outcome = repair_cluster_representative_image(
            client,
            "cluster-1",
            "https://example.com/logo.png",
            check_reachability=False,
        )

    assert outcome == "replaced"
    mock_db.execute.assert_called()


def test_repair_cluster_representative_image_clears_when_no_candidate():
    client = MagicMock()
    with patch("tasks.maintenance.db") as mock_db:
        mock_db.execute.return_value = []

        outcome = repair_cluster_representative_image(
            client,
            "cluster-2",
            "https://example.com/logo.png",
            check_reachability=False,
        )

    assert outcome == "cleared"
