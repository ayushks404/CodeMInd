import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import mongoose from "mongoose";

import auth_routes from "./src/routes/auth_routes.js";
import project_routes from "./src/routes/project_routes.js";
import query_routes from "./src/routes/query_routes.js";


dotenv.config();

const app = express();

// CORS: only allow requests from our frontend origin
// app.use(cors()) with no options = any domain can call this API
// That means a random website could make authenticated requests on behalf of my users

app.use(cors({
  origin: process.env.FRONTEND_URL || "http://localhost:5173",
  credentials: true,   // needed if frontend sends cookies / auth headers
}));

app.use(express.json());




app.get("/", (req, res) => {
  res.send("backend running");
});
 
app.use("/api/auth", auth_routes);
app.use("/api/project", project_routes);
app.use("/api/query", query_routes);
 

const connectdb = async () => {
    try{
        await mongoose.connect(process.env.MONGO_URI);
        console.log("mongodb connected");
    }
    catch (err){
        console.log("db error" , err.message);
        process.exit(1);
    }
};





const PORT = process.env.PORT;
app.listen(PORT , () =>{
    console.log("server running on port 5000");
});

connectdb();



