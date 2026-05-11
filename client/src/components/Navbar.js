import { FiLogOut } from "react-icons/fi";
import { useNavigate } from "react-router-dom";

function Navbar() {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem("token");
    navigate("/login");
  };

  return (
    <div className="sidebar">
      <button onClick={handleLogout}>
        <FiLogOut /> Sign Out
      </button>
    </div>
  );
}

export default Navbar;
