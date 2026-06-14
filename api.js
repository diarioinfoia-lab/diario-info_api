// ❌ NO dotenv at cPanel
require("dotenv").config();

const express = require("express");
const mongoose = require("mongoose");
const path = require("path");
const api = express();

// =======================
// Middlewares
// =======================
api.use((req, res, next) => {
  // Headers CORS allowed
  res.setHeader("Access-Control-Allow-Origin", "*");

  // Headers methods allowed
  res.setHeader(
    "Access-Control-Allow-Methods",
    "GET, POST, PUT, PATCH, DELETE, OPTIONS",
  );

  // Headers allowed
  res.setHeader(
    "Access-Control-Allow-Headers",
    "Origin, X-Requested-With, Accept, Content-Type, Authorization",
  );

  // Headers no-cache
  res.setHeader(
    "Cache-Control",
    "no-store, no-cache, must-revalidate, proxy-revalidate",
  );
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Expires", "0");
  res.setHeader("Surrogate-Control", "no-store");

  // Continue to routes
  next();
});

api.use(express.json());

// =======================
// Static Files
// =======================
api.use("/uploads", express.static(path.join(__dirname, "uploads")));

// =======================
// Routes
// =======================
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

// =======================
// Health check
// =======================
api.get("/health", (req, res) => {
  res.json({
    status: "ok",
    env: process.env.NODE_ENV || "unknown",
    mongo: mongoose.connection.readyState === 1 ? "connected" : "disconnected",
  });
});

// =======================
// Start server (Passenger)
// =======================
const PORT = process.env.PORT || 3000;

api.listen(PORT, () => {
  console.log(`🚀 API listening on port ${PORT}`);

  // =======================
  // Mongo connection (SAFE)
  // =======================
  const getConnectionString = require("./utils/mongo_db").getConnectionString;


           (async () => {
               let conn;
               try {
                     conn = getConnectionString();
               } catch (err) {
                     console.error("❌ Mongo config error:", err.message);
                     return; // Stop if config is invalid
               }

              if (!conn) {
                    console.warn("⚠️ MongoDB not configured");
                    return;
              }

              if (mongoose.connection.readyState === 0) {
                    mongoose.set("strictQuery", false);
                    try {
                            await mongoose.connect(conn, {
                                      serverSelectionTimeoutMS: 10000,
                                      family: 4,
                            });
                            console.log("✅ MongoDB connected");
                    } catch (err) {
                            console.error("❌ MongoDB connection failed:", err.message);
                    }
              }
           })();
