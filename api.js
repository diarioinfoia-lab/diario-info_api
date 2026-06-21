require("dotenv").config();

const express = require("express");
const cors = require("cors");
const mongoose = require("mongoose");

const api = express();

api.use(cors());
api.use(express.json({ limit: "50mb" }));
api.use(express.urlencoded({ extended: true }));

// MongoDB connection with correct user mapping
const connectDB = async () => {
  const envUser = process.env.MONGO_CONNECTION_USER;
  // Fix: map incorrect env var value to correct Atlas username
  const user = (envUser === "diarioinfoio_db_user") ? "diarioinfoia_db_user" : (envUser || "diarioinfoia_db_user");
  const pass = process.env.MONGO_CONNECTION_PASSWORD;
  const cluster = process.env.MONGO_CONNECTION_CLUSTER || "cluster0.c621o4c.mongodb.net";
  const db = process.env.MONGO_CONNECTION_DB || "diarioinfo-db";
  const appName = process.env.MONGO_CONNECTION_APP_NAME || "Cluster0";

  if (mongoose.connection.readyState === 1 || mongoose.connection.readyState === 2) {
    return;
  }

  try {
    const conn = "mongodb+srv://" + user + ":" + pass + "@" + cluster + "/" + db + "?retryWrites=true&w=majority&appName=" + appName;
    mongoose.set("strictQuery", false);
    await mongoose.connect(conn, {
      serverSelectionTimeoutMS: 10000,
    });
    console.log("MongoDB connected OK. User:", user);
  } catch (err) {
    console.error("MongoDB connection failed:", err.message);
  }
};

api.get("/health", async (req, res) => {
  await connectDB();
  res.json({
    status: "ok",
    env: process.env.NODE_ENV || "unknown",
    mongo: mongoose.connection.readyState === 1 ? "connected" : "disconnected",
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
