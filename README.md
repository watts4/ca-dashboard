# 🏫 CA Schools AI Dashboard

*Making California school performance data accessible through natural language AI*

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Available-green?style=for-the-badge)](cadashboard.wattswattswatts.com)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue?style=for-the-badge&logo=github)](https://github.com/watts4/ca-dashboard)

## 🎯 Overview

The CA Schools AI Dashboard transforms complex California Department of Education data into an intuitive, conversational interface. Users can ask natural language questions about school performance and receive intelligent, contextual responses backed by comprehensive state data.

**Try asking:** *"Which schools in San Jose have math concerns for English Learner students?"* or *"Show me high-performing ELA schools in San Francisco"*

## ✨ Key Features

### 🤖 AI-Powered Natural Language Processing
- **Intelligent Query Parsing**: Converts conversational questions into precise database queries
- **Context Understanding**: Recognizes educational terminology, demographics, and performance indicators
- **Smart Response Generation**: Provides analytical insights, not just raw data

### 📊 Comprehensive School Data
- **7 Performance Indicators**: Chronic Absenteeism, ELA, Math, Suspensions, College/Career Readiness, Graduation Rates, English Learner Progress
- **17 Student Demographics**: All racial/ethnic groups, English learners, special education, socioeconomically disadvantaged, foster youth, homeless students
- **50,000+ School Records**: Complete coverage of California public schools

### 🎨 Interactive Results
- **Dynamic Tables**: Sortable, filterable performance data
- **Demographic Switching**: View results by student group with one click
- **Color-Coded Performance**: Visual indicators from Red (concerning) to Blue (excellent)
- **Responsive Design**: Works seamlessly on desktop and mobile

## 🛠 Technology Stack

### Google Cloud Platform
- **Vertex AI (Gemini 2.0 Flash)**: Natural language processing and intelligent response generation
- **Cloud Run**: Serverless deployment and auto-scaling
- **AI Platform**: Model inference and API management

### MongoDB
- **Document Storage**: Flexible schema for complex nested school data
- **Advanced Querying**: Regex search, conditional filtering, aggregation pipelines
- **Atlas Cloud**: Managed database with global availability

### Application Framework
- **Python Flask**: Lightweight web framework
- **JavaScript**: Interactive frontend with dynamic content rendering
- **HTML/CSS**: Responsive design with modern UI/UX

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- MongoDB Atlas account
- Google Cloud Platform account with Vertex AI enabled

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/ca-schools-dashboard.git
   cd ca-schools-dashboard
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials:
   # MONGODB_URI=your_mongodb_connection_string
   # PROJECT_ID=your_google_cloud_project_id
   ```

4. **Import school data**
   ```bash
   python data_import_improved.py
   ```

5. **Run the application**
   ```bash
   python app.py
   ```

6. **Open your browser**
   ```
   http://localhost:8080
   ```

## 📁 Data Sources

All data sourced from the [California Department of Education Dashboard](https://www.cde.ca.gov/ta/ac/cm/acaddatafiles.asp):

- `chronicdownload2024.csv` - Chronic Absenteeism rates
- `eladownload2024.csv` - English Language Arts performance
- `mathdownload2024.csv` - Mathematics performance  
- `suspdownload2024.csv` - Suspension rates
- `ccidownload2024.csv` - College/Career Indicator
- `graddownload2024.csv` - Graduation rates
- `elpidownload2024.csv` - English Learner Progress Indicator

## 🔧 Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User Query    │───▶│   Vertex AI      │───▶│   Query Parser  │
│ "Schools in SF" │    │ (Gemini 2.0)     │    │   (MongoDB)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  User Interface │◀───│  AI Response     │◀───│   School Data   │
│   (Results)     │    │  Generation      │    │   (MongoDB)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🎬 Demo Examples

### Parent/Guardian Queries
- *"Which elementary schools in San Francisco have strong reading performance?"*
- *"Show me schools with low chronic absenteeism in San Diego"*

### Educational Research
- *"Achievement gaps between ethnic groups in Los Angeles Unified"*
- *"English learner progress across different school types"*

### Policy & Advocacy
- *"Schools with concerning suspension rates for students with disabilities"*
- *"College readiness trends in rural California districts"*

## 🌟 Impact

### Educational Equity
- **Democratizes Data Access**: Makes state educational data accessible to non-technical users
- **Supports Advocacy**: Enables community members to identify schools needing support
- **Informs Decision Making**: Helps parents make informed school choices

### Technical Innovation
- **Hybrid AI Approach**: Combines LLM intelligence with reliable pattern matching
- **Scalable Architecture**: Serverless deployment handles varying traffic
- **Public Service**: Free, open-source tool for community benefit

## 🔒 Security & Rate Limiting

- **IP-based Rate Limiting**: 10 queries per minute, 200 per hour
- **Input Sanitization**: All user queries are validated and sanitized
- **No Personal Data**: Only aggregated, public school performance data

## 🚀 Deployment

### Google Cloud Run
```bash
# Build and deploy
gcloud run deploy ca-schools-dashboard \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### Environment Variables
- `MONGODB_URI`: MongoDB Atlas connection string
- `PROJECT_ID`: Google Cloud project ID
- `PORT`: Application port (default: 8080)

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Setup
1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and test thoroughly
4. Submit a pull request with a clear description

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🏆 Hackathon Submission

This project was built for the **AI in Action Hackathon** sponsored by Google Cloud and MongoDB.

**Challenge**: MongoDB Challenge - Using AI and MongoDB to make public data more accessible and actionable.

## 📞 Contact

- **Developer**: [Your Name](mailto:jonathanwatts@gmail.com)
- **Project**: [Live Demo](cadashboard.wattswattswatts.com)
- **Repository**: [GitHub](https://github.com/watts4/ca-dashboard)

---

*Built with ❤️ for educational equity and data accessibility*