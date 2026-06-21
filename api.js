require("dotenv").config();

const express = require("express");
const path = require("path");
const mongoose = require("mongoose");

const api = express();
let lastMongoError = null;

// CORS headers
api.use((req, res, next) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Origin, X-Requested-With, Content-Type, Accept, Authorization, x-client-version");
    if (req.method === "OPTIONS") {
        return res.sendStatus(200);
    }
    next();
});

api.use(express.json({ limit: "30mb" }));
api.use(express.urlencoded({ extended: true, limit: "30mb" }));
api.use("/uploads", express.static(path.join(__dirname, "uploads")));

// MongoDB connection - tries ia cluster first, falls back to api2 cluster
const connectDB = async () => {
    if (mongoose.connection.readyState === 1 || mongoose.connection.readyState === 2) {
        return;
    }
    // Use env vars if provided, otherwise use api2 cluster defaults
    const user = process.env.MONGO_CONNECTION_USER || "diarioinfoia_db_user";
    const pass = process.env.MONGO_CONNECTION_PASSWORD;
    const cluster = process.env.MONGO_CONNECTION_CLUSTER || "cluster0.wypjl60.mongodb.net";
    const db = process.env.MONGO_CONNECTION_DB || "diario-info-db";
    const appName = process.env.MONGO_CONNECTION_APP_NAME || "Cluster0";

    try {
        const conn = "mongodb+srv://" + user + ":" + pass + "@" + cluster + "/" + db + "?retryWrites=true&w=majority&appName=" + appName;
        mongoose.set("strictQuery", false);
        await mongoose.connect(conn, {
            serverSelectionTimeoutMS: 10000,
        });
        lastMongoError = null;
        console.log("MongoDB connected. Cluster:", cluster, "DB:", db);
    } catch (err) {
        lastMongoError = err.message;
        console.error("MongoDB connection failed:", err.message);
    }
};

api.get("/health", async (req, res) => {
    await connectDB();
    res.json({
        status: "ok",
        env: process.env.NODE_ENV || "unknown",
        mongo: mongoose.connection.readyState === 1 ? "connected" : "disconnected",
        mongoError: lastMongoError,
        cluster: process.env.MONGO_CONNECTION_CLUSTER || "cluster0.wypjl60.mongodb.net",
        db: process.env.MONGO_CONNECTION_DB || "diario-info-db",
    });
});

api.use(async (req, res, next) => {
    await connectDB();
    next();
});

api.use(require("./routes/auth.router"));
api.use(require("./routes/user.router"));
api.use(require("./routes/file.router"));
api.use(require("./routes/block.router"));
api.use(require("./routes/article.router"));
api.use(require("./routes/category.router"));
api.use(require("./routes/notification.router"));
api.use(require("./routes/importer.router"));
api.use(require("./routes/bot.router"));
api.use(require("./routes/playlist.router"));
api.use(require("./routes/log.router"));

module.exports = api;
