import { Routes, Route } from "react-router-dom";

import Layout from "./components/Layout";
import UploadAnalyze from "./pages/UploadAnalyze";
import ReviewDashboard from "./pages/ReviewDashboard";
import History from "./pages/History";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<UploadAnalyze />} />
        <Route path="dashboard" element={<ReviewDashboard />} />
        <Route path="history" element={<History />} />
      </Route>
    </Routes>
  );
}
