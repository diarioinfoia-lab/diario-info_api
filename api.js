require("dotenv").config();

const express = require("express");
const path = require("path");
const mongoose = require("mongoose");

const api = express();
let lastMongoError = null;
let connectedCluster = null;

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

// Try connecting to a MongoDB cluster with given params
const tryConnect = async (user, pass, cluster, db, appName) => {
    const conn = "mongodb+srv://" + user + ":" + pass + "@" + cluster + "/" + db + "?retryWrites=true&w=majority&appName=" + appName;
    mongoose.set("strictQuery", false);
    await mongoose.connect(conn, { serverSelectionTimeoutMS: 8000 });
    connectedCluster = cluster;
    console.log("MongoDB connected to:", cluster, "DB:", db);
};

const connectDB = async () => {
    if (mongoose.connection.readyState === 1 || mongoose.connection.readyState === 2) {
        return;
    }

    const envUser = process.env.MONGO_CONNECTION_USER;
    const envPass = process.env.MONGO_CONNECTION_PASSWORD;
    const envCluster = process.env.MONGO_CONNECTION_CLUSTER;
    const envDb = process.env.MONGO_CONNECTION_DB;
    const envApp = process.env.MONGO_CONNECTION_APP_NAME || "Cluster0";

    // First try env vars (ia cluster or whatever is configured)
    if (envUser && envPass && envCluster) {
        try {
            await tryConnect(envUser, envPass, envCluster, envDb || "diario-info-db", envApp);
            lastMongoError = null;
            return;
        } catch (err) {
            console.warn("Primary cluster failed:", err.message.substring(0, 100));
        }
    }

    // Fallback to api2 own cluster
    try {
        await tryConnect("diarioinfoia_db_user", envPass || "", "cluster0.wypjl60.mongodb.net", "diario-info-db", "Cluster0");
        lastMongoError = null;
    } catch (err) {
        lastMongoError = err.message;
        console.error("All clusters failed:", err.message.substring(0, 100));
    }
};

api.get("/health", async (req, res) => {
    await connectDB();
    res.json({
        status: "ok",
        env: process.env.NODE_ENV || "unknown",
        mongo: mongoose.connection.readyState === 1 ? "connected" : "disconnected",
        connectedCluster,
        mongoError: lastMongoError,
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

api.use(require('./routes/pdf.router'));
api.use(require('./routes/rewrite.router'));

module.exports = api;
