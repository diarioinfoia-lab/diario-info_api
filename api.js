require("dotenv").config();

const express = require("express");
const mongoose = require("mongoose");
const path = require("path");
const api = express();

const { getConnectionString } = require("./utils/mongo_db");

const connectDB = async () => {
    if (mongoose.connection.readyState === 1) return;
    if (mongoose.connection.readyState === 2) {
        await new Promise((resolve) => mongoose.connection.once("connected", resolve));
        return;
    }
    try {
        const conn = getConnectionString();
        mongoose.set("strictQuery", false);
        await mongoose.connect(conn, {
            serverSelectionTimeoutMS: 10000,
            family: 4,
        });
        console.log("MongoDB connected OK");
    } catch (err) {
        console.error("MongoDB connection failed:", err.message);
    }
};

api.use((req, res, next) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Origin, X-Requested-With, Content-Type, Accept, Authorization, x-client-version");
    if (req.method === "OPTIONS") return res.status(200).json({});
    next();
});

api.use(express.json({ limit: "30mb" }));
api.use(express.urlencoded({ extended: true, limit: "30mb" }));
api.use("/uploads", express.static(path.join(__dirname, "uploads")));

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

api.get("/health", (req, res) => {
    res.json({
        status: "ok",
        env: process.env.NODE_ENV || "unknown",
        mongo: mongoose.connection.readyState === 1 ? "connected" : "disconnected",
    });
});

module.exports = api;
