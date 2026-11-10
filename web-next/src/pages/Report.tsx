import { Link, useParams } from "react-router-dom";
import { getReport } from "../services/reportCache";
import ReportView from "../components/report/ReportView";
import "./scan.css";

export default function ReportPage() {
  const { id } = useParams();
  const r = id ? getReport(id) : null;
  return (
    <section className="wrap scan">
      <h1>Report</h1>
      {r ? <ReportView r={r} /> : (
        <div className="glass panel">
          <p>This report is not stored in this browser. The server has no fetch-by-id endpoint, so older reports can only be re-run.</p>
          <div className="row"><Link className="btn primary" to="/scan">Run a new scan</Link></div>
        </div>
      )}
    </section>
  );
}