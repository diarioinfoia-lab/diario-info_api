const mongoose = require("mongoose");

const connectMongoDB = async () => {
  // Atlas user: diarioinfoia_db_user
  const MONGO_USER = process.env.MONGO_CONNECTION_USER || "diarioinfoia_db_user";
  const MONGO_PASS = process.env.MONGO_CONNECTION_PASSWORD;
  const MONGO_CLUSTER = process.env.MONGO_CONNECTION_CLUSTER || "cluster0.c621o4c.mongodb.net";
  const MONGO_DB = process.env.MONGO_CONNECTION_DB || "diarioinfo-db";
  const MONGO_APP = process.env.MONGO_CONNECTION_APP_NAME || "Cluster0";

  const uri = "mongodb+srv://" + MONGO_USER + ":" + MONGO_PASS + "@" + MONGO_CLUSTER + "/" + MONGO_DB + "?retryWrites=true&w=majority&appName=" + MONGO_APP;

  try {
    await mongoose.connect(uri);
    console.log("MongoDB connected successfully");
  } catch (error) {
    console.error("MongoDB connection error:", error);
    throw error;
  }
};

module.exports = connectMongoDB;
