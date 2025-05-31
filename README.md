# GradeLens HAC API

A FastAPI-based backend for accessing Frisco ISD Home Access Center (HAC) data.

## Endpoints

### POST /api/info

Get student personal information including name, ID, grade, campus, birthdate, and counselor.

**Request Body:**

```json
{
    "username": "your_hac_username",
    "password": "your_hac_password"
}
```

**Response:**

```json
{
    "name": "Doe, John",
    "id": "123456",
    "grade": "12",
    "campus": "Independence High School",
    "birthdate": "01/01/2006",
    "counselor": "Smith, Jane"
}
```

### POST /api/schedule

Get student class schedule.

**Request Body:**

```json
{
    "username": "your_hac_username",
    "password": "your_hac_password"
}
```

**Response:**

```json
{
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
}
```

### POST /api/currentclasses

Get current classes with assignments and grades.

**Request Body:**

```json
{
    "username": "your_hac_username",
    "password": "your_hac_password"
}
```

**Response:**

```json
{
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
}
```

### POST /api/all

Get all student data in one request (combines info, schedule, and classes).

**Request Body:**

```json
{
    "username": "your_hac_username",
    "password": "your_hac_password"
}
```

**Response:**

```json
{
  "studentInfo": { ... },
  "studentSchedule": [ ... ],
  "currentClasses": [ ... ]
}
```

## Local Development

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the server:

```bash
uvicorn main:app --reload --port 8000
```

3. Access the API documentation at: http://localhost:8000/docs

## Deployment to Vercel

1. Install Vercel CLI:

```bash
npm install -g vercel
```

2. Deploy:

```bash
vercel --prod
```

## CORS Configuration

The API is configured to allow all origins for development. In production, update the `allow_origins` in the CORS middleware to specify your frontend domain.

## Error Handling

All endpoints return a 401 status code with "Invalid credentials" message if authentication fails or if there's an error accessing HAC data.

## Security Notes

-   This API requires HAC credentials to function
-   Credentials are not stored - they're only used for the duration of the request
-   All communication should be over HTTPS in production
-   Consider implementing rate limiting for production use
