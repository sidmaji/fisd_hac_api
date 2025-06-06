from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="FISD HAC API", version="1.0.0")

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


class ClassesRequest(BaseModel):
    username: str
    password: str
    quarter: str = "current"  # Default to current quarter


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

    student_name = soup.find(id="plnMain_lblRegStudentName").text
    student_birthdate = soup.find(id="plnMain_lblBirthDate").text
    student_counselor = soup.find(id="plnMain_lblCounselor").text
    student_campus = soup.find(id="plnMain_lblBuildingName").text
    student_grade = soup.find(id="plnMain_lblGrade").text
    total_credits = 0

    # Try to get the student id from the registration page
    # If this fails, try to get the student id from the student schedule page
    try:
        student_id = soup.find(id="plnMain_lblRegStudentID").text
    except:
        schedule_page_content = session.get(
            f"{HAC_BASE_URL}/HomeAccess/Content/Student/Classes.aspx"
        ).text
        schedule_parser = BeautifulSoup(schedule_page_content, "lxml")
        student_id = schedule_parser.find(id="plnMain_lblRegStudentID").text

    return {
        "id": student_id,
        "name": student_name,
        "birthdate": student_birthdate,
        "campus": student_campus,
        "grade": student_grade,
        "counselor": student_counselor,
        "totalCredits": str(total_credits),
    }


def get_student_schedule(session: requests.Session) -> List[Dict[str, Any]]:
    """Extract student schedule"""
    response = session.get(f"{HAC_BASE_URL}/HomeAccess/Content/Student/Classes.aspx")
    soup = BeautifulSoup(response.text, "lxml")

    schedule = []

    try:
        courses = soup.find_all("tr", "sg-asp-table-data-row")

        for row in courses:
            parser = BeautifulSoup(f"<html><body>{row}</body></html>", "lxml")
            tds = [x.text.strip() for x in parser.find_all("td")]

            if len(tds) > 3:
                # Extract teacher email from the teacher column (index 3)
                teacher_cell = parser.find_all("td")[3]
                teacher_email = ""
                teacher_name = tds[3]

                # Check if there's a mailto link in the teacher cell
                mailto_link = teacher_cell.find("a", href=True)
                if mailto_link and mailto_link["href"].startswith("mailto:"):
                    teacher_email = mailto_link["href"].replace("mailto:", "").strip()

                schedule.append(
                    {
                        "building": tds[7],
                        "courseCode": tds[0],
                        "courseName": tds[1],
                        "days": tds[5],
                        "markingPeriods": tds[6],
                        "periods": tds[2],
                        "room": tds[4],
                        "status": tds[8],
                        "teacher": teacher_name,
                        "teacherEmail": teacher_email,
                    }
                )
    except Exception as e:
        print(f"Error parsing schedule: {e}")

    return schedule


def get_classes(
    session: requests.Session, quarter: str = "current"
) -> List[Dict[str, Any]]:
    """Extract classes with assignments and grades for current or past quarters"""

    if quarter == "current":
        # Get current classes - same as before
        response = session.get(
            f"{HAC_BASE_URL}/HomeAccess/Content/Student/Assignments.aspx"
        )
        course_content = response.text
    else:
        # Get past classes for specific quarter
        headers = {
            "Host": "hac.friscoisd.org",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:98.0) Gecko/20100101 Firefox/98.0",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://hac.friscoisd.org",
            "Referer": "https://hac.friscoisd.org/HomeAccess/Content/Student/Assignments.aspx",
        }

        # First get the current page to extract viewstate and other required fields
        initial_response = session.get(
            f"{HAC_BASE_URL}/HomeAccess/Content/Student/Assignments.aspx"
        )
        initial_soup = BeautifulSoup(initial_response.text, "lxml")

        # Extract required form fields
        viewstate = initial_soup.find("input", {"name": "__VIEWSTATE"})["value"]
        viewstate_generator = initial_soup.find(
            "input", {"name": "__VIEWSTATEGENERATOR"}
        )["value"]
        event_validation = initial_soup.find("input", {"name": "__EVENTVALIDATION"})[
            "value"
        ]

        payload = {
            "__EVENTTARGET": "ctl00$plnMain$btnRefreshView",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": viewstate_generator,
            "__EVENTVALIDATION": event_validation,
            "ctl00$plnMain$hdnValidMHACLicense": "Y",
            "ctl00$plnMain$hdnIsVisibleClsWrk": "N",
            "ctl00$plnMain$hdnIsVisibleCrsAvg": "N",
            "ctl00$plnMain$hdnJsAlert": "Averages+cannot+be+displayed+when++Report+Card+Run+is+set+to+(All+Runs).",
            "ctl00$plnMain$hdnTitle": "Classwork",
            "ctl00$plnMain$hdnLastUpdated": "Last+Updated",
            "ctl00$plnMain$hdnDroppedCourse": "+This+course+was+dropped+as+of+",
            "ctl00$plnMain$hdnddlClasses": "(All+Classes)",
            "ctl00$plnMain$hdnddlCompetencies": "(All+Classes)",
            "ctl00$plnMain$hdnCompDateDue": "Date+Due",
            "ctl00$plnMain$hdnCompDateAssigned": "Date+Assigned",
            "ctl00$plnMain$hdnCompCourse": "Course",
            "ctl00$plnMain$hdnCompAssignment": "Assignment",
            "ctl00$plnMain$hdnCompAssignmentLabel": "Assignments+Not+Related+to+Any+Competency",
            "ctl00$plnMain$hdnCompNoAssignments": "No+assignments+found",
            "ctl00$plnMain$hdnCompNoClasswork": "Classwork+could+not+be+found+for+this+competency+for+the+selected+report+card+run.",
            "ctl00$plnMain$hdnCompScore": "Score",
            "ctl00$plnMain$hdnCompPoints": "Points",
            "ctl00$plnMain$hdnddlReportCardRuns1": "(All+Runs)",
            "ctl00$plnMain$hdnddlReportCardRuns2": "(All+Terms)",
            "ctl00$plnMain$hdnbtnShowAverage": "Show+All+Averages",
            "ctl00$plnMain$hdnShowAveragesToolTip": "Show+all+student's+averages",
            "ctl00$plnMain$hdnPrintClassworkToolTip": "Print+all+classwork",
            "ctl00$plnMain$hdnPrintClasswork": "Print+Classwork",
            "ctl00$plnMain$hdnCollapseToolTip": "Collapse+all+courses",
            "ctl00$plnMain$hdnCollapse": "Collapse+All",
            "ctl00$plnMain$hdnFullToolTip": "Switch+courses+to+Full+View",
            "ctl00$plnMain$hdnViewFull": "Full+View",
            "ctl00$plnMain$hdnQuickToolTip": "Switch+courses+to+Quick+View",
            "ctl00$plnMain$hdnViewQuick": "Quick+View",
            "ctl00$plnMain$hdnExpand": "Expand+All",
            "ctl00$plnMain$hdnExpandToolTip": "Expand+all+courses",
            "ctl00$plnMain$hdnChildCompetencyMessage": "This+competency+is+calculated+as+an+average+of+the+following+competencies",
            "ctl00$plnMain$hdnCompetencyScoreLabel": "Grade",
            "ctl00$plnMain$hdnAverageDetailsDialogTitle": "Average+Details",
            "ctl00$plnMain$hdnAssignmentCompetency": "Assignment+Competency",
            "ctl00$plnMain$hdnAssignmentCourse": "Assignment+Course",
            "ctl00$plnMain$hdnTooltipTitle": "Title",
            "ctl00$plnMain$hdnCategory": "Category",
            "ctl00$plnMain$hdnDueDate": "Due+Date",
            "ctl00$plnMain$hdnMaxPoints": "Max+Points",
            "ctl00$plnMain$hdnCanBeDropped": "Can+Be+Dropped",
            "ctl00$plnMain$hdnHasAttachments": "Has+Attachments",
            "ctl00$plnMain$hdnExtraCredit": "Extra+Credit",
            "ctl00$plnMain$hdnType": "Type",
            "ctl00$plnMain$hdnAssignmentDataInfo": "Information+could+not+be+found+for+the+assignment",
            "ctl00$plnMain$ddlReportCardRuns": f"{quarter}-2025",
            "ctl00$plnMain$ddlClasses": "ALL",
            "ctl00$plnMain$ddlCompetencies": "ALL",
            "ctl00$plnMain$ddlOrderBy": "Class",
        }

        response = session.post(
            f"{HAC_BASE_URL}/HomeAccess/Content/Student/Assignments.aspx",
            data=payload,
            headers=headers,
        )
        course_content = response.text

    # Parse the response (same logic for both current and past)
    soup = BeautifulSoup(course_content, "lxml")
    courses = []

    try:
        # Find all class containers
        courseContainer = soup.find_all("div", "AssignmentClass")

        for container in courseContainer:
            newCourse = {"name": "", "grade": "", "lastUpdated": "", "assignments": []}
            parser = BeautifulSoup(f"<html><body>{container}</body></html>", "lxml")
            headerContainer = parser.find_all("div", "sg-header sg-header-square")
            assignementsContainer = parser.find_all("div", "sg-content-grid")

            # Flag to track if this course should be skipped
            skip_course = False

            for hc in headerContainer:
                parser = BeautifulSoup(f"<html><body>{hc}</body></html>", "lxml")

                # Check if this course is dropped by looking for the DroppedCourse span
                dropped_course_span = parser.find("span", "DroppedCourse")
                if dropped_course_span:
                    # Mark this course to be skipped
                    skip_course = True
                    break

                newCourse["name"] = parser.find("a", "sg-header-heading").text.strip()

                # Find the last updated span that's not the dropped course span
                last_updated_span = parser.find("span", "sg-header-sub-heading")
                if last_updated_span and "DroppedCourse" not in last_updated_span.get(
                    "class", []
                ):
                    newCourse["lastUpdated"] = (
                        last_updated_span.text.strip()
                        .replace("(Last Updated: ", "")
                        .replace(")", "")
                    )
                else:
                    newCourse["lastUpdated"] = ""

                newCourse["grade"] = (
                    parser.find("span", "sg-header-heading sg-right")
                    .text.strip()
                    .replace("Student Grades ", "")
                    .replace("%", "")
                )

            # Skip processing this course if it's dropped
            if skip_course:
                continue

            for ac in assignementsContainer:
                parser = BeautifulSoup(f"<html><body>{ac}</body></html>", "lxml")
                rows = parser.find_all("tr", "sg-asp-table-data-row")
                for assignmentContainer in rows:
                    try:
                        parser = BeautifulSoup(
                            f"<html><body>{assignmentContainer}</body></html>", "lxml"
                        )
                        tds = parser.find_all("td")
                        assignmentName = parser.find("a").text.strip()
                        assignmentDateDue = tds[0].text.strip()
                        assignmentDateAssigned = tds[1].text.strip()
                        assignmentCategory = tds[3].text.strip()
                        assignmentScore = tds[4].text.strip()
                        assignmentTotalPoints = tds[5].text.strip()

                        newCourse["assignments"].append(
                            {
                                "name": assignmentName,
                                "category": assignmentCategory,
                                "dateAssigned": assignmentDateAssigned,
                                "dateDue": assignmentDateDue,
                                "score": assignmentScore,
                                "totalPoints": assignmentTotalPoints,
                            }
                        )
                    except:
                        pass

            courses.append(newCourse)

    except Exception as e:
        print(f"Error parsing classes: {e}")

    return courses


def get_student_transcript(session: requests.Session) -> List[Dict[str, Any]]:
    """Extract student transcript data"""
    response = session.get(f"{HAC_BASE_URL}/HomeAccess/Content/Student/Transcript.aspx")
    soup = BeautifulSoup(response.text, "lxml")

    transcript_data = []

    try:
        # Find all transcript groups
        transcript_groups = soup.find_all("td", "sg-transcript-group")

        for index, group in enumerate(transcript_groups):
            group_parser = BeautifulSoup(f"<html><body>{group}</body></html>", "lxml")
            tables = group_parser.find_all("table")

            if len(tables) >= 3:
                header_table = tables[0]
                courses_table = tables[1]
                credits_table = tables[2]

                # Extract header information
                header_parser = BeautifulSoup(
                    f"<html><body>{header_table}</body></html>", "lxml"
                )
                year_attended = header_parser.find(
                    "span", id=f"plnMain_rpTranscriptGroup_lblYearValue_{index}"
                ).text.strip()
                grade_level = header_parser.find(
                    "span", id=f"plnMain_rpTranscriptGroup_lblGradeValue_{index}"
                ).text.strip()
                school_building = header_parser.find(
                    "span", id=f"plnMain_rpTranscriptGroup_lblBuildingValue_{index}"
                ).text.strip()

                # Extract course details
                courses_parser = BeautifulSoup(
                    f"<html><body>{courses_table}</body></html>", "lxml"
                )
                course_rows = courses_parser.find_all("tr", "sg-asp-table-data-row")

                course_list = []
                for course_row in course_rows:
                    row_parser = BeautifulSoup(
                        f"<html><body>{course_row}</body></html>", "lxml"
                    )
                    course_cells = row_parser.find_all("td")

                    if len(course_cells) >= 6:
                        course_code = course_cells[0].text.strip()
                        course_name = course_cells[1].text.strip()
                        semester1_grade = course_cells[2].text.strip()
                        semester2_grade = course_cells[3].text.strip()
                        final_grade = course_cells[4].text.strip()
                        credit_hours = course_cells[5].text.strip()

                        course_list.append(
                            {
                                "courseCode": course_code,
                                "courseName": course_name,
                                "sem1Grade": semester1_grade,
                                "sem2Grade": semester2_grade,
                                "finalGrade": final_grade,
                                "courseCredits": credit_hours,
                            }
                        )

                # Extract total credits
                credits_parser = BeautifulSoup(
                    f"<html><body>{credits_table}</body></html>", "lxml"
                )
                total_credits = credits_parser.find(
                    "label", id=f"plnMain_rpTranscriptGroup_LblTCreditValue_{index}"
                ).text

                transcript_data.append(
                    {
                        "yearsAttended": year_attended,
                        "gradeLevel": grade_level,
                        "building": school_building,
                        "totalCredits": total_credits,
                        "courses": course_list,
                    }
                )

    except Exception as e:
        print(f"Error parsing transcript: {e}")

    return transcript_data


def get_student_gpa(session: requests.Session) -> Dict[str, Any]:
    """Extract student GPA information"""
    response = session.get(f"{HAC_BASE_URL}/HomeAccess/Content/Student/Transcript.aspx")
    soup = BeautifulSoup(response.text, "lxml")

    gpa_data = {
        "unweightedGPA": "",
        "weightedGPA": "",
        "rank": None,
    }

    try:
        # Extract weighted and unweighted GPA
        weighted_gpa_element = soup.find(id="plnMain_rpTranscriptGroup_lblGPACum1")
        unweighted_gpa_element = soup.find(id="plnMain_rpTranscriptGroup_lblGPACum2")

        if weighted_gpa_element:
            gpa_data["weightedGPA"] = weighted_gpa_element.text.strip()

        if unweighted_gpa_element:
            gpa_data["unweightedGPA"] = unweighted_gpa_element.text.strip()

        # Try to extract class rank (may not be available for all students)
        try:
            rank_element = soup.find(id="plnMain_rpTranscriptGroup_lblGPARank1")
            if rank_element:
                gpa_data["rank"] = rank_element.text.strip()
        except:
            pass

    except Exception as e:
        print(f"Error parsing GPA: {e}")

    return gpa_data


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
        <title>FISD HAC API</title>
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
                <h1>🎓 FISD HAC API</h1>
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
                    <div class="description">Get student class schedule with periods, rooms, teachers, and teacher emails.</div>
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
      "teacherEmail": "smithj@friscoisd.org",
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
                    <h3><span class="method">POST</span>/api/classes</h3>
                    <div class="description">Get classes for a specific quarter (1, 2, 3, 4) or current quarter. Supports quarter parameter.</div>
                    <div class="code-block">
                        <pre>Request Body:
{
  "username": "your_username",
  "password": "your_password",
  "quarter": "1"  // or "2", "3", "4", "current"
}

Response:
{
  "pastClasses": [
    {
      "name": "MTH45300B - 2    AP Calculus AB S2",
      "grade": "99.00",
      "lastUpdated": "4/17/2025",
      "assignments": [
        {
          "name": "Area & Cross Sections Test",
          "category": "Assessment of Learning",
          "dateAssigned": "",
          "dateDue": "04/15/2025",
          "score": "95.00",
          "totalPoints": "100.00"
        }
      ]
    }
  ]
}</pre>
                    </div>
                </div>

                <div class="endpoint">
                    <h3><span class="method">POST</span>/api/transcript</h3>
                    <div class="description">Get student transcript with all courses, grades, and credits by year.</div>
                    <div class="code-block">
                        <pre>{
  "studentTranscript": [
    {
      "yearsAttended": "2022-2023",
      "gradeLevel": "11",
      "building": "Independence High School",
      "totalCredits": "7.5000",
      "courses": [
        {
          "courseCode": "A3220100 - 1",
          "courseName": "AP ENG LANG",
          "sem1Grade": "88",
          "sem2Grade": "92",
          "finalGrade": "",
          "courseCredits": "1.0000"
        },
        {
          "courseCode": "A3100900 - 1",
          "courseName": "AP CALC AB",
          "sem1Grade": "95",
          "sem2Grade": "97",
          "finalGrade": "",
          "courseCredits": "1.0000"
        }
      ]
    }
  ]
}</pre>
                    </div>
                </div>

                <div class="endpoint">
                    <h3><span class="method">POST</span>/api/gpa</h3>
                    <div class="description">Get student GPA information including weighted, unweighted, and class rank.</div>
                    <div class="code-block">
                        <pre>{
  "unweightedGPA": "3.8500",
  "weightedGPA": "4.9200",
  "rank": "42 / 387"
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
                            <option value="/api/classes">Classes (with Quarter)</option>
                            <option value="/api/transcript">Transcript</option>
                            <option value="/api/gpa">GPA & Rank</option>
                            <option value="/api/all">All Data</option>
                        </select>
                    </div>

                    <button class="btn" onclick="testAPI()">Test API</button>

                    <div id="response" class="response"></div>
                </div>
            </div>

            <div class="footer">
                <p>Not affiliated with Frisco ISD • Made by Siddhant Maji • FISD HAC API • v1.0.0</p>
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
        classes = get_classes(session, "current")

        return {"currentClasses": classes}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/classes")
async def get_classes_endpoint(request: ClassesRequest):
    """Get classes with assignments and grades for specified quarter"""
    try:
        session = getRequestSession(request.username, request.password)
        classes = get_classes(session, request.quarter)

        # Return different key based on quarter type
        if request.quarter == "current":
            return {"currentClasses": classes}
        else:
            return {"pastClasses": classes}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/all")
async def get_all_data_endpoint(request: LoginRequest):
    """Get all student data in one request"""
    try:
        session = getRequestSession(request.username, request.password)

        info = get_student_info(session)
        schedule = get_student_schedule(session)
        classes = get_classes(session, "current")

        if not info:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return {
            "studentInfo": info,
            "studentSchedule": schedule,
            "currentClasses": classes,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/transcript")
async def get_student_transcript_endpoint(request: LoginRequest):
    """Get student transcript with all courses and grades"""
    try:
        session = getRequestSession(request.username, request.password)
        transcript = get_student_transcript(session)

        return {"studentTranscript": transcript}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/gpa")
async def get_student_gpa_endpoint(request: LoginRequest):
    """Get student GPA and class rank information"""
    try:
        session = getRequestSession(request.username, request.password)
        gpa_info = get_student_gpa(session)

        return gpa_info
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
