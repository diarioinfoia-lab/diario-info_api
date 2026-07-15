const mongoose = require("mongoose");
const { Schema } = mongoose;

const PollOptionSchema = new Schema(
  {
        text: { type: String, required: true },
        votes: { type: Number, default: 0 },
  },
  { _id: true }
  );

const PollSchema = new Schema(
  {
        title: { type: String, required: true },
        description: { type: String },
        slug: { type: String, unique: true, sparse: true },
        options: {
                type: [PollOptionSchema],
                validate: {
                          validator: (arr) => Array.isArray(arr) && arr.length >= 2,
                          message: "A poll needs at least 2 options",
                },
        },
        article: { type: Schema.Types.ObjectId, ref: "Article", default: null },
        status: {
                type: String,
                enum: ["draft", "active", "closed"],
          default: "draft",
        },
        isSensitive: { type: Boolean, default: false },
        startDate: { type: Date, default: null },
        endDate: { type: Date, default: null },
        settings: {
                oneVotePerDevice: { type: Boolean, default: true },
                showResultsBeforeVote: { type: Boolean, default: false },
                showResultsAfterVote: { type: Boolean, default: true },
                showResultsAfterClose: { type: Boolean, default: true },
                maxVotesPerIpPerHour: { type: Number, default: 3 },
        },
        totalVotes: { type: Number, default: 0 },
        flagged: { type: Boolean, default: false },
        flagReason: { type: String, default: null },
        createdBy: { type: Schema.Types.ObjectId, ref: "User" },
        disabledAt: { type: Date, default: null },
  },
  { timestamps: true }
  );

PollSchema.index({ status: 1, createdAt: -1 });
PollSchema.index({ article: 1 });

const Poll = mongoose.models.Poll || mongoose.model("Poll", PollSchema);
module.exports = Poll;
