import unittest

from foli_harvester.parsers import parse_alerts_payload, parse_delay_seconds, parse_vm_payload


class ParserTests(unittest.TestCase):
    def test_parse_delay_seconds_accepts_iso_and_numeric_values(self):
        self.assertEqual(parse_delay_seconds("PT1M30S"), 90)
        self.assertEqual(parse_delay_seconds("-PT45S"), -45)
        self.assertEqual(parse_delay_seconds("PT1H2M3S"), 3723)
        self.assertEqual(parse_delay_seconds(12), 12)
        self.assertEqual(parse_delay_seconds("-30"), -30)
        self.assertEqual(parse_delay_seconds("0"), 0)
        self.assertIsNone(parse_delay_seconds(None))
        self.assertIsNone(parse_delay_seconds("not-a-duration"))

    def test_parse_vm_payload_extracts_trip_matching_fields(self):
        parsed = parse_vm_payload(
            {
                "status": "OK",
                "servertime": 1433246786,
                "result": {
                    "vehicles": {
                        "550011": {
                            "vehicleref": "550011",
                            "recordedattime": 1433246781,
                            "validuntiltime": 1433247381,
                            "lineref": "14",
                            "directionref": "1",
                            "originaimeddeparturetime": 1433258100,
                            "latitude": 60.431302,
                            "longitude": 22.240084,
                            "delay": "PT1M30S",
                            "incongestion": False,
                            "monitored": True,
                            "next_stoppointref": "81",
                        }
                    }
                },
            }
        )

        self.assertEqual(parsed.status, "OK")
        self.assertEqual(len(parsed.observations), 1)
        row = parsed.observations[0]
        self.assertEqual(row["line_ref"], "14")
        self.assertEqual(row["direction_ref"], "1")
        self.assertEqual(row["origin_aimed_departure_unix"], 1433258100)
        self.assertEqual(row["trip_match_key"], "14|1|1433258100")
        self.assertIs(row["is_gtfs_matchable"], True)
        self.assertEqual(row["delay_seconds"], 90)

    def test_parse_vm_payload_marks_missing_trip_fields_unmatchable(self):
        parsed = parse_vm_payload(
            {
                "status": "OK",
                "result": {
                    "vehicles": {
                        "bus": {
                            "vehicleref": "bus",
                            "lineref": "14",
                            "directionref": "1",
                        }
                    }
                },
            }
        )

        row = parsed.observations[0]
        self.assertIsNone(row["trip_match_key"])
        self.assertIs(row["is_gtfs_matchable"], False)

    def test_parse_vm_payload_handles_pending_and_no_siri_data(self):
        pending = parse_vm_payload({"status": "PENDING", "servertime": 1, "result": []})
        no_data = parse_vm_payload({"status": "NO_SIRI_DATA", "servertime": 1, "result": []})
        self.assertEqual(pending.status, "PENDING")
        self.assertEqual(pending.observations, [])
        self.assertEqual(no_data.status, "NO_SIRI_DATA")
        self.assertEqual(no_data.observations, [])

    def test_parse_alerts_payload_accepts_missing_optional_fields(self):
        parsed = parse_alerts_payload(
            {
                "servertime": 1587723597,
                "messages": [
                    {
                        "message_id": 123,
                        "message": "Poikkeusreitti",
                        "affected_routes": ["14"],
                        "repeat": [[1587720000, 1587730000]],
                        "isactive": True,
                    }
                ],
                "cancellations": [
                    {
                        "line": "2A",
                        "departure": 1587723300,
                        "stops": [{"stop": "1651", "isactive": True}],
                    }
                ],
            }
        )

        self.assertEqual(len(parsed.alerts), 2)
        message = parsed.alerts[0]
        cancellation = parsed.alerts[1]
        self.assertEqual(message["alert_type"], "message")
        self.assertEqual(message["source_alert_id"], "123")
        self.assertEqual(message["line_ref"], "14")
        self.assertEqual(cancellation["alert_type"], "cancellation")
        self.assertEqual(cancellation["line_ref"], "2A")
        self.assertIs(cancellation["is_active"], True)


if __name__ == "__main__":
    unittest.main()
