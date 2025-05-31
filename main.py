import re
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="GradeLens HAC API", version="1.0.0")

# Enable CORS for SPA frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
HAC_BASE_URL = "https://hac.friscoisd.org"


# Request models
class LoginRequest(BaseModel):
    username: str
    password: str


# Helper Functions
def getRequestSession(username: str, password: str) -> requests.Session:
    requestSession = requests.Session()

    # Fetch the login page to get the verification token
    loginScreenResponse = requestSession.get(
        f"{HAC_BASE_URL}/HomeAccess/Account/LogOn?ReturnUrl=%2fHomeAccess%2f"
    ).text

    parser = BeautifulSoup(loginScreenResponse, "lxml")
    requestVerificationToken = parser.find(
        "input", attrs={"name": "__RequestVerificationToken"}
    )["value"]

    # Prepare headers and payload for login
    requestHeaders = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.125 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Host": "hac.friscoisd.org",
        "Origin": "hac.friscoisd.org",
        "Referer": "https://hac.friscoisd.org/HomeAccess/Account/LogOn?ReturnUrl=%2fhomeaccess%2f",
        "__RequestVerificationToken": requestVerificationToken,
    }

    requestPayload = {
        "__RequestVerificationToken": requestVerificationToken,
        "SCKTY00328510CustomEnabled": "False",
        "SCKTY00436568CustomEnabled": "False",
        "Database": "10",
        "VerificationOption": "UsernamePassword",
        "LogOnDetails.UserName": username,
        "tempUN": "",
        "tempPW": "",
        "LogOnDetails.Password": password,
    }

    # Perform login
    requestSession.post(
        f"{HAC_BASE_URL}/HomeAccess/Account/LogOn?ReturnUrl=%2fHomeAccess%2f",
        data=requestPayload,
        headers=requestHeaders,
    )

    return requestSession


def get_student_info(session: requests.Session) -> Dict[str, Any]:
    """Extract student personal information"""
    response = session.get(
        f"{HAC_BASE_URL}/HomeAccess/Content/Student/Registration.aspx"
    )
    soup = BeautifulSoup(response.text, "lxml")

    student_info = {}

    try:
        # Find student name
        name_element = soup.find("span", {"id": "plnMain_lblRegStudentName"})
        if name_element:
            student_info["name"] = name_element.text.strip()

        # Find student ID
        id_element = soup.find("span", {"id": "plnMain_lblRegStudentID"})
        if id_element:
            student_info["id"] = id_element.text.strip()

        # Find grade
        grade_element = soup.find("span", {"id": "plnMain_lblRegGrade"})
        if grade_element:
            student_info["grade"] = grade_element.text.strip()

        # Find campus
        campus_element = soup.find("span", {"id": "plnMain_lblRegCampus"})
        if campus_element:
            student_info["campus"] = campus_element.text.strip()

        # Find birthdate
        birth_element = soup.find("span", {"id": "plnMain_lblRegBirthDate"})
        if birth_element:
            student_info["birthdate"] = birth_element.text.strip()

        # Find counselor
        counselor_element = soup.find("span", {"id": "plnMain_lblRegCounselor"})
        if counselor_element:
            student_info["counselor"] = counselor_element.text.strip()

    except Exception as e:
        print(f"Error parsing student info: {e}")

    return student_info


def get_student_schedule(session: requests.Session) -> List[Dict[str, Any]]:
    """Extract student schedule"""
    response = session.get(f"{HAC_BASE_URL}/HomeAccess/Content/Student/Classes.aspx")
    soup = BeautifulSoup(response.text, "lxml")

    schedule = []

    try:
        # Find the schedule table
        schedule_table = soup.find("table", {"class": "sg-asp-table"})
        if schedule_table:
            rows = schedule_table.find_all("tr")[1:]  # Skip header row

            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 7:
                    course_info = {
                        "building": cells[0].text.strip(),
                        "courseCode": cells[1].text.strip(),
                        "courseName": cells[2].text.strip(),
                        "periods": cells[3].text.strip(),
                        "days": cells[4].text.strip(),
                        "room": cells[5].text.strip(),
                        "teacher": cells[6].text.strip(),
                        "markingPeriods": (
                            cells[7].text.strip() if len(cells) > 7 else ""
                        ),
                        "status": "Active",
                    }
                    schedule.append(course_info)
    except Exception as e:
        print(f"Error parsing schedule: {e}")

    return schedule


def get_current_classes(session: requests.Session) -> List[Dict[str, Any]]:
    """Extract current classes with assignments and grades"""
    response = session.get(
        f"{HAC_BASE_URL}/HomeAccess/Content/Student/Assignments.aspx"
    )
    soup = BeautifulSoup(response.text, "lxml")

    classes = []

    try:
        # Find all class containers
        class_containers = soup.find_all("div", {"class": "AssignmentClass"})

        for container in class_containers:
            class_info = {}

            # Get class name and grade
            class_header = container.find(
                "div", {"class": "sg-header sg-header-square"}
            )
            if class_header:
                class_name_element = class_header.find(
                    "a", {"class": "sg-header-heading"}
                )
                if class_name_element:
                    class_info["name"] = class_name_element.text.strip()

                # Look for grade in the header
                grade_match = re.search(r"(\d+\.?\d*)%?", class_header.text)
                if grade_match:
                    class_info["grade"] = grade_match.group(1)
                else:
                    class_info["grade"] = ""

            # Get class details (weight, credits, etc.)
            class_info["weight"] = "5"  # Default weight
            class_info["credits"] = "1"  # Default credits
            class_info["lastUpdated"] = ""

            # Get assignments
            assignments = []
            assignment_table = container.find("table", {"class": "sg-asp-table"})

            if assignment_table:
                assignment_rows = assignment_table.find_all("tr")[1:]  # Skip header

                for row in assignment_rows:
                    cells = row.find_all("td")
                    if len(cells) >= 6:
                        assignment = {
                            "name": cells[2].text.strip(),
                            "category": cells[3].text.strip(),
                            "dateAssigned": cells[0].text.strip(),
                            "dateDue": cells[1].text.strip(),
                            "score": cells[4].text.strip(),
                            "totalPoints": cells[5].text.strip(),
                        }
                        assignments.append(assignment)

            class_info["assignments"] = assignments
            classes.append(class_info)

    except Exception as e:
        print(f"Error parsing classes: {e}")

    return classes


# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the API documentation page"""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GradeLens HAC API</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #333;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }

            .header {
                text-align: center;
                color: white;
                margin-bottom: 40px;
            }

            .header h1 {
                font-size: 3rem;
                margin-bottom: 10px;
                font-weight: 700;
            }

            .header p {
                font-size: 1.2rem;
                opacity: 0.9;
            }

            .content {
                background: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            }

            .endpoint {
                background: #f8f9fa;
                border-radius: 10px;
                padding: 25px;
                margin-bottom: 30px;
                border-left: 5px solid #007bff;
            }

            .endpoint h3 {
                color: #007bff;
                margin-bottom: 15px;
                font-size: 1.5rem;
            }

            .method {
                background: #28a745;
                color: white;
                padding: 5px 12px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 0.9rem;
                margin-right: 10px;
            }

            .url {
                font-family: 'Monaco', 'Consolas', monospace;
                background: #e9ecef;
                padding: 10px;
                border-radius: 5px;
                margin: 15px 0;
                font-size: 0.95rem;
            }

            .description {
                margin: 15px 0;
                color: #666;
            }

            .code-block {
                background: #f1f3f4;
                border-radius: 8px;
                padding: 20px;
                margin: 15px 0;
                overflow-x: auto;
            }

            .code-block pre {
                font-family: 'Monaco', 'Consolas', monospace;
                font-size: 0.9rem;
                margin: 0;
            }

            .test-section {
                background: #fff3cd;
                border: 1px solid #ffeaa7;
                border-radius: 10px;
                padding: 25px;
                margin-top: 30px;
            }

            .test-section h3 {
                color: #856404;
                margin-bottom: 15px;
            }

            .form-group {
                margin-bottom: 15px;
            }

            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: 600;
            }

            .form-group input, .form-group select {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 16px;
            }

            .btn {
                background: #007bff;
                color: white;
                padding: 12px 25px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                transition: all 0.3s;
            }

            .btn:hover {
                background: #0056b3;
                transform: translateY(-2px);
            }

            .response {
                margin-top: 20px;
                padding: 15px;
                border-radius: 5px;
                display: none;
            }

            .response.success {
                background: #d4edda;
                border: 1px solid #c3e6cb;
                color: #155724;
            }

            .response.error {
                background: #f8d7da;
                border: 1px solid #f5c6cb;
                color: #721c24;
            }

            .footer {
                text-align: center;
                margin-top: 40px;
                color: white;
                opacity: 0.8;
            }

            @media (max-width: 768px) {
                .container {
                    padding: 15px;
                }

                .header h1 {
                    font-size: 2rem;
                }

                .content {
                    padding: 25px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎓 GradeLens HAC API</h1>
                <p>Access Frisco ISD Home Access Center data programmatically</p>
            </div>

            <div class="content">
                <div class="endpoint">
                    <h3><span class="method">POST</span>/api/info</h3>
                    <div class="description">Get student personal information including name, ID, grade, campus, birthdate, and counselor.</div>
                    <div class="code-block">
                        <pre>{
  "name": "Doe, John",
  "id": "123456",
  "grade": "12",
  "campus": "Independence High School",
  "birthdate": "01/01/2006",
  "counselor": "Smith, Jane"
}</pre>
                    </div>
                </div>

                <div class="endpoint">
                    <h3><span class="method">POST</span>/api/schedule</h3>
                    <div class="description">Get student class schedule with periods, rooms, and teachers.</div>
                    <div class="code-block">
                        <pre>{
  "studentSchedule": [
    {
      "building": "Independence High School",
      "courseCode": "MTH45300A - 1",
      "courseName": "AP Calculus AB S1",
      "periods": "1",
      "days": "A",
      "room": "B201",
      "teacher": "Smith, John",
      "markingPeriods": "Q1, Q2",
      "status": "Active"
    }
  ]
}</pre>
                    </div>
                </div>

                <div class="endpoint">
                    <h3><span class="method">POST</span>/api/currentclasses</h3>
                    <div class="description">Get current classes with assignments, grades, and due dates.</div>
                    <div class="code-block">
                        <pre>{
  "currentClasses": [
    {
      "name": "MTH45300A - 1    AP Calculus AB S1",
      "grade": "95.5",
      "weight": "5",
      "credits": "1",
      "lastUpdated": "01/15/2025",
      "assignments": [
        {
          "name": "Unit 1 Test",
          "category": "Major Grades",
          "dateAssigned": "01/10/2025",
          "dateDue": "01/15/2025",
          "score": "98",
          "totalPoints": "100"
        }
      ]
    }
  ]
}</pre>
                    </div>
                </div>

                <div class="endpoint">
                    <h3><span class="method">POST</span>/api/all</h3>
                    <div class="description">Get all student data in one request (most efficient for apps).</div>
                    <div class="code-block">
                        <pre>{
  "studentInfo": { ... },
  "studentSchedule": [ ... ],
  "currentClasses": [ ... ]
}</pre>
                    </div>
                </div>

                <div class="test-section">
                    <h3>🧪 Test the API</h3>
                    <p>Enter your HAC credentials to test the endpoints:</p>

                    <div class="form-group">
                        <label for="username">Username:</label>
                        <input type="text" id="username" placeholder="Enter your HAC username">
                    </div>

                    <div class="form-group">
                        <label for="password">Password:</label>
                        <input type="password" id="password" placeholder="Enter your HAC password">
                    </div>

                    <div class="form-group">
                        <label for="endpoint">Endpoint:</label>
                        <select id="endpoint">
                            <option value="/api/info">Student Info</option>
                            <option value="/api/schedule">Class Schedule</option>
                            <option value="/api/currentclasses">Current Classes</option>
                            <option value="/api/all">All Data</option>
                        </select>
                    </div>

                    <button class="btn" onclick="testAPI()">Test API</button>

                    <div id="response" class="response"></div>
                </div>
            </div>

            <div class="footer">
                <p>Built for GradeLens • Frisco ISD HAC API • v1.0.0</p>
            </div>
        </div>

        <script>
            async function testAPI() {
                const username = document.getElementById('username').value;
                const password = document.getElementById('password').value;
                const endpoint = document.getElementById('endpoint').value;
                const responseDiv = document.getElementById('response');

                if (!username || !password) {
                    responseDiv.className = 'response error';
                    responseDiv.style.display = 'block';
                    responseDiv.innerHTML = 'Please enter both username and password.';
                    return;
                }

                try {
                    responseDiv.className = 'response';
                    responseDiv.style.display = 'block';
                    responseDiv.innerHTML = 'Testing API endpoint...';

                    const response = await fetch(endpoint, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            username: username,
                            password: password
                        })
                    });

                    const data = await response.json();

                    if (response.ok) {
                        responseDiv.className = 'response success';
                        responseDiv.innerHTML = '<strong>Success!</strong><br><pre>' + JSON.stringify(data, null, 2) + '</pre>';
                    } else {
                        responseDiv.className = 'response error';
                        responseDiv.innerHTML = '<strong>Error:</strong> ' + (data.detail || 'Unknown error occurred');
                    }
                } catch (error) {
                    responseDiv.className = 'response error';
                    responseDiv.innerHTML = '<strong>Error:</strong> ' + error.message;
                }
            }
        </script>
    </body>
    </html>
    """


@app.post("/api/info")
async def get_student_info_endpoint(request: LoginRequest):
    """Get student personal information"""
    try:
        session = getRequestSession(request.username, request.password)
        info = get_student_info(session)

        if not info:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return info
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/schedule")
async def get_student_schedule_endpoint(request: LoginRequest):
    """Get student class schedule"""
    try:
        session = getRequestSession(request.username, request.password)
        schedule = get_student_schedule(session)

        return {"studentSchedule": schedule}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/currentclasses")
async def get_current_classes_endpoint(request: LoginRequest):
    """Get current classes with assignments and grades"""
    try:
        session = getRequestSession(request.username, request.password)
        classes = get_current_classes(session)

        return {"currentClasses": classes}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/all")
async def get_all_data_endpoint(request: LoginRequest):
    """Get all student data in one request"""
    try:
        session = getRequestSession(request.username, request.password)

        info = get_student_info(session)
        schedule = get_student_schedule(session)
        classes = get_current_classes(session)

        if not info:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return {
            "studentInfo": info,
            "studentSchedule": schedule,
            "currentClasses": classes,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
