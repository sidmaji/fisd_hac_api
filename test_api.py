# Test the API endpoints locally
import json

import requests

# Base URL for local testing
BASE_URL = "http://localhost:8000"

# Test credentials (replace with actual HAC credentials)
TEST_CREDENTIALS = {"username": "username", "password": "password"}


def test_endpoint(endpoint, description):
    """Test an API endpoint"""
    print(f"\n{'='*50}")
    print(f"Testing: {description}")
    print(f"Endpoint: {endpoint}")
    print(f"{'='*50}")

    try:
        response = requests.post(f"{BASE_URL}{endpoint}", json=TEST_CREDENTIALS)

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("Response (formatted):")
            print(json.dumps(data, indent=2))
        else:
            print(f"Error: {response.text}")

    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to API. Make sure the server is running.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print("GradeLens HAC API Test Script")
    print("Make sure to:")
    print("1. Update TEST_CREDENTIALS with real HAC username/password")
    print("2. Start the API server with: uvicorn main:app --reload")

    # Test all endpoints
    test_endpoint("/api/info", "Student Information")
    test_endpoint("/api/schedule", "Student Schedule")
    test_endpoint("/api/currentclasses", "Current Classes")
    test_endpoint("/api/all", "All Data Combined")

    print(f"\n{'='*50}")
    print("Testing complete!")
    print(f"{'='*50}")
