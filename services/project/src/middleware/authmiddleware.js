import axios from "axios";

export const protect = async (req, res, next) => {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return res.status(401).json({ message: "No token provided" });
  }

  const token = authHeader.split(" ")[1];

  try {
    // Architecture Section 9.1: services must not share JWT_SECRET.
    // Delegate verification to the auth service instead of calling jwt.verify() directly.
    const AUTH_SERVICE = process.env.AUTH_SERVICE_URL || "http://auth:5001";
    const { data } = await axios.post(
      `${AUTH_SERVICE}/api/auth/verify`,
      { token },
      { timeout: 5000 }
    );

    if (!data.valid) {
      return res.status(401).json({ message: "Token invalid or expired" });
    }

    // Middleware sets req.user with _id so controllers work unchanged.
    req.user = { _id: data.user_id };

    next();
  } catch (err) {
    console.error("Auth verify call failed:", err.message);
    return res.status(401).json({ message: "Token invalid or expired" });
  }
};