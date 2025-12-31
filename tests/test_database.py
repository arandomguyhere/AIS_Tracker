"""
Database functionality tests for AIS_Tracker.
"""

import unittest
import sqlite3
from datetime import datetime, timedelta

from tests.base import BaseTestCase, TestDatabase


class TestDatabaseSchema(BaseTestCase):
    """Test database schema and structure."""

    def test_vessels_table_exists(self):
        """Verify vessels table exists with required columns."""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vessels'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_positions_table_exists(self):
        """Verify positions table exists."""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='positions'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_alerts_table_exists(self):
        """Verify alerts table exists."""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alerts'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_watchlist_table_exists(self):
        """Verify watchlist table exists."""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='watchlist'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_shipyards_table_exists(self):
        """Verify shipyards table exists."""
        cursor = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='shipyards'"
        )
        self.assertIsNotNone(cursor.fetchone())

    def test_wal_mode_can_be_enabled(self):
        """Verify WAL mode can be enabled."""
        self.db.execute("PRAGMA journal_mode=WAL")
        result = self.db.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(result.lower(), 'wal')


class TestVesselOperations(BaseTestCase):
    """Test vessel CRUD operations."""

    def test_insert_vessel(self):
        """Test inserting a vessel."""
        vessel_id = self.insert_test_vessel(name='INSERT TEST', mmsi='111111111')
        self.assertIsNotNone(vessel_id)
        self.assertGreater(vessel_id, 0)

    def test_retrieve_vessel(self):
        """Test retrieving a vessel by ID."""
        vessel_id = self.insert_test_vessel(name='RETRIEVE TEST', mmsi='222222222')
        cursor = self.db.execute('SELECT * FROM vessels WHERE id = ?', (vessel_id,))
        vessel = cursor.fetchone()
        self.assertIsNotNone(vessel)
        self.assertEqual(vessel['name'], 'RETRIEVE TEST')
        self.assertEqual(vessel['mmsi'], '222222222')

    def test_update_vessel(self):
        """Test updating a vessel."""
        vessel_id = self.insert_test_vessel(name='UPDATE TEST', mmsi='333333333')
        self.db.execute(
            'UPDATE vessels SET name = ? WHERE id = ?',
            ('UPDATED NAME', vessel_id)
        )
        self.db.commit()

        cursor = self.db.execute('SELECT name FROM vessels WHERE id = ?', (vessel_id,))
        vessel = cursor.fetchone()
        self.assertEqual(vessel['name'], 'UPDATED NAME')

    def test_delete_vessel(self):
        """Test deleting a vessel."""
        vessel_id = self.insert_test_vessel(name='DELETE TEST', mmsi='444444444')
        self.db.execute('DELETE FROM vessels WHERE id = ?', (vessel_id,))
        self.db.commit()

        cursor = self.db.execute('SELECT * FROM vessels WHERE id = ?', (vessel_id,))
        self.assertIsNone(cursor.fetchone())

    def test_vessel_required_fields(self):
        """Test that required fields are enforced."""
        # Name should be required
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT INTO vessels (mmsi) VALUES (?)', ('555555555',))


class TestPositionOperations(BaseTestCase):
    """Test position tracking operations."""

    def test_insert_position(self):
        """Test inserting a position record."""
        vessel_id = self.insert_test_vessel(name='POSITION TEST', mmsi='666666666')
        self.insert_test_position(vessel_id, 45.5, 13.5)

        cursor = self.db.execute(
            'SELECT * FROM positions WHERE vessel_id = ?', (vessel_id,)
        )
        position = cursor.fetchone()
        self.assertIsNotNone(position)
        self.assertAlmostEqual(position['latitude'], 45.5, places=4)
        self.assertAlmostEqual(position['longitude'], 13.5, places=4)

    def test_position_history(self):
        """Test retrieving position history."""
        vessel_id = self.insert_test_vessel(name='HISTORY TEST', mmsi='777777777')

        # Insert multiple positions
        for i in range(5):
            timestamp = (datetime.utcnow() - timedelta(hours=i)).isoformat()
            self.insert_test_position(
                vessel_id,
                45.5 + i * 0.01,
                13.5 + i * 0.01,
                timestamp=timestamp
            )

        cursor = self.db.execute(
            'SELECT COUNT(*) as count FROM positions WHERE vessel_id = ?',
            (vessel_id,)
        )
        count = cursor.fetchone()['count']
        self.assertEqual(count, 5)


class TestAlertOperations(BaseTestCase):
    """Test alert system operations."""

    def test_create_alert(self):
        """Test creating an alert."""
        vessel_id = self.insert_test_vessel(name='ALERT TEST', mmsi='888888888')

        self.db.execute('''
            INSERT INTO alerts (vessel_id, alert_type, severity, title, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (vessel_id, 'proximity', 'high', 'Test Alert', 'Test alert message'))
        self.db.commit()

        cursor = self.db.execute(
            'SELECT * FROM alerts WHERE vessel_id = ?', (vessel_id,)
        )
        alert = cursor.fetchone()
        self.assertIsNotNone(alert)
        self.assertEqual(alert['alert_type'], 'proximity')
        self.assertEqual(alert['severity'], 'high')

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        vessel_id = self.insert_test_vessel(name='ACK TEST', mmsi='999999999')

        self.db.execute('''
            INSERT INTO alerts (vessel_id, alert_type, severity, title, message, acknowledged)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (vessel_id, 'test', 'low', 'Ack Test', 'Ack test message', 0))
        self.db.commit()

        cursor = self.db.execute('SELECT id FROM alerts WHERE vessel_id = ?', (vessel_id,))
        alert_id = cursor.fetchone()['id']

        self.db.execute('UPDATE alerts SET acknowledged = 1 WHERE id = ?', (alert_id,))
        self.db.commit()

        cursor = self.db.execute('SELECT acknowledged FROM alerts WHERE id = ?', (alert_id,))
        self.assertEqual(cursor.fetchone()['acknowledged'], 1)


class TestWatchlistOperations(BaseTestCase):
    """Test watchlist operations."""

    def test_add_to_watchlist(self):
        """Test adding a vessel to watchlist."""
        vessel_id = self.insert_test_vessel(name='WATCHLIST TEST', mmsi='101010101')

        self.db.execute('''
            INSERT INTO watchlist (vessel_id, priority, notes)
            VALUES (?, ?, ?)
        ''', (vessel_id, 1, 'Test reason'))
        self.db.commit()

        cursor = self.db.execute(
            'SELECT * FROM watchlist WHERE vessel_id = ?', (vessel_id,)
        )
        entry = cursor.fetchone()
        self.assertIsNotNone(entry)
        self.assertEqual(entry['notes'], 'Test reason')
        self.assertEqual(entry['priority'], 1)


if __name__ == '__main__':
    unittest.main()
