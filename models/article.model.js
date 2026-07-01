const mongoose = require("mongoose");
const { Schema } = mongoose;

const ArticleSchema = new Schema(
  {
    title: { type: String, required: true, trim: true },
    slug: { type: String, trim: true, unique: true },
    description: { type: String, trim: true, required: true },
    content: { type: String, required: true }, // Replaces contentBlocks
    imageId: { type: String },
    category: { type: Schema.Types.ObjectId, ref: "Category", required: true },
    status: {
      type: String,
      required: true,
      enum: ["draft", "published", "review"],
      default: "draft",
    },
    isHighlighted: { type: Boolean, default: false },
    author: { type: String },
    authorColor: { type: String },
    authorPrefixColor: { type: String },
    createdBy: { type: Schema.Types.ObjectId, ref: "User" },
    date: { type: String },
    location: { type: String },
    publicationDate: { type: Date },
    commentsDisabled: { type: Boolean, default: false },
    embeddedVideoUrl: { type: String },
    keyPoints: [{ type: String }],
    priority: {
      type: Number,
      required: true,
      default: 0,
    },
    destination: { type: String },
    validityHours: { type: Number, default: 24 },
    tags: { type: [String], index: true },
    articleType: { type: String },
  },
  {
    timestamps: true, // Automatically adds createdAt and updatedAt
  },
);

// Transform _id to id for frontend compatibility
ArticleSchema.set("toJSON", {
  virtuals: true,
  versionKey: false,
  transform: function (doc, ret) {
    ret.id = ret._id;
    delete ret._id;
  },
});

// Indexes to optimize common queries
ArticleSchema.index({ status: 1, createdAt: -1 });
ArticleSchema.index({ category: 1, status: 1 });
ArticleSchema.index({
  status: 1,
  publicationDate: -1,
  priority: -1,
});

// Prevent Mongoose from compiling the model more than once
const Article =
  mongoose.models.Article || mongoose.model("Article", ArticleSchema);

module.exports = Article;
