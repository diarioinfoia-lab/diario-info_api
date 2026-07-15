const Poll = require("../models/poll.model.js");
const PollVote = require("../models/pollVote.model.js");
const Log = require("../models/log.model.js");
const mongoose = require("mongoose");
const crypto = require("crypto");

const HASH_SALT = process.env.POLL_HASH_SALT || "diarioinfo_poll_salt_v1";

const hash = (value) =>
  crypto.createHash("sha256").update(HASH_SALT + "|" + value).digest("hex");

const getClientIp = (req) => {
  const fwd = req.headers["x-forwarded-for"];
  if (fwd) return fwd.split(",")[0].trim();
  return req.socket?.remoteAddress || req.ip || "unknown";
};

const getSubnet = (ip) => {
  if (!ip || ip === "unknown") return "unknown";
  if (ip.includes(".")) {
    const parts = ip.split(".");
    return parts.slice(0, 3).join(".") + ".0/24";
  }
  const parts = ip.split(":");
  return parts.slice(0, 3).join(":") + "::/48";
};

const parseUserAgent = (ua) => {
  if (!ua) return { browser: "unknown", os: "unknown", deviceType: "unknown" };
  const browser = /Edg\//.test(ua)
  ? "Edge"
    : /Chrome\//.test(ua)
  ? "Chrome"
    : /Firefox\//.test(ua)
  ? "Firefox"
    : /Safari\//.test(ua) && !/Chrome/.test(ua)
  ? "Safari"
    : "other";
  const os = /Windows/.test(ua)
  ? "Windows"
    : /Android/.test(ua)
  ? "Android"
    : /iPhone|iPad|iOS/.test(ua)
  ? "iOS"
    : /Mac OS/.test(ua)
  ? "macOS"
    : /Linux/.test(ua)
  ? "Linux"
    : "other";
  const deviceType = /Mobile|Android|iPhone/.test(ua) ? "mobile" : "desktop";
  return { browser, os, deviceType };
};

const generateSlug = (text) => {
  if (!text) return "";
  return text
  .toString()
  .toLowerCase()
  .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
  .replace(/\s+/g, "-")
  .replace(/[^\w\-]+/g, "")
  .replace(/\-\-+/g, "-")
  .replace(/^-+/, "")
  .replace(/-+$/, "");
};

// ---- ADMIN ENDPOINTS ----

exports.createPoll = async (req, res) => {
  if (!req.userId) return res.status(401).send({ message: "Unauthorized" });
  const { title, description, options, article, isSensitive, startDate, endDate, settings, slug } = req.body;

  if (!title || !Array.isArray(options) || options.length < 2) {
    return res.status(400).send({ message: "Title and at least 2 options are required" });
  }

  try {
    const poll = new Poll({
      title,
      description,
      slug: slug || generateSlug(title) + "-" + Date.now().toString(36),
      options: options.map((o) => ({ text: typeof o === "string" ? o : o.text, votes: 0 })),
      article: article || null,
      isSensitive: !!isSensitive,
      startDate: startDate || null,
      endDate: endDate || null,
      settings: { ...{}, ...(settings || {}) },
      createdBy: req.userId,
      status: "draft",
    });
    const data = await poll.save();

  const log = new Log({ user: req.userId, action: "POLL_CREATED", details: `Poll "${data.title}" (${data._id}) created` });
    await log.save();

  res.status(201).send({ success: true, poll: data });
  } catch (err) {
    res.status(500).send({ message: err.message || "Error creating poll" });
  }
};

exports.getPolls = async (req, res) => {
  const { status, article } = req.query;
  const page = parseInt(req.query.page) || 1;
  const pageSize = parseInt(req.query.pageSize) || 20;
  const condition = { disabledAt: null };
  if (status) condition.status = status;
  if (article) condition.article = article;

  try {
    const total = await Poll.countDocuments(condition);
    const polls = await Poll.find(condition)
    .sort({ createdAt: -1 })
    .skip((page - 1) * pageSize)
    .limit(pageSize);
    res.send({ success: true, polls, total, totalPages: Math.ceil(total / pageSize) });
  } catch (err) {
    res.status(500).send({ message: err.message || "Error retrieving polls" });
  }
};

exports.getPoll = async (req, res) => {
  const id = req.params.id;
  try {
    const condition = { disabledAt: null };
    let data = id.match(/^[0-9a-fA-F]{24}$/)
    ? await Poll.findOne({ _id: id, ...condition })
      : null;
    if (!data) data = await Poll.findOne({ slug: id, ...condition });
    if (!data) return res.status(404).send({ message: "Poll not found" });

  const result = data.toObject();
    if (!data.settings.showResultsBeforeVote && data.status !== "closed") {
      result.options = result.options.map((o) => ({ _id: o._id, text: o.text }));
      result.totalVotes = undefined;
    }
    res.send({ success: true, poll: result });
  } catch (err) {
    res.status(500).send({ message: "Error retrieving poll" });
  }
};

exports.updatePoll = async (req, res) => {
  if (!req.userId) return res.status(401).send({ message: "Unauthorized" });
  const id = req.params.id;
  try {
    const data = await Poll.findByIdAndUpdate(id, req.body, { new: true });
    if (!data) return res.status(404).send({ message: "Poll not found" });
    const log = new Log({ user: req.userId, action: "POLL_UPDATED", details: `Poll ${id} updated` });
    await log.save();
    res.send({ success: true, poll: data });
  } catch (err) {
    res.status(500).send({ message: "Error updating poll" });
  }
};

exports.closePoll = async (req, res) => {
  if (!req.userId) return res.status(401).send({ message: "Unauthorized" });
  const id = req.params.id;
  try {
    const data = await Poll.findByIdAndUpdate(id, { status: "closed", endDate: new Date() }, { new: true });
    if (!data) return res.status(404).send({ message: "Poll not found" });
    const log = new Log({ user: req.userId, action: "POLL_CLOSED", details: `Poll ${id} closed` });
    await log.save();
    res.send({ success: true, poll: data });
  } catch (err) {
    res.status(500).send({ message: "Error closing poll" });
  }
};

exports.activatePoll = async (req, res) => {
  if (!req.userId) return res.status(401).send({ message: "Unauthorized" });
  const id = req.params.id;
  try {
    const data = await Poll.findByIdAndUpdate(id, { status: "active", startDate: new Date() }, { new: true });
    if (!data) return res.status(404).send({ message: "Poll not found" });
    const log = new Log({ user: req.userId, action: "POLL_ACTIVATED", details: `Poll ${id} activated` });
    await log.save();
    res.send({ success: true, poll: data });
  } catch (err) {
    res.status(500).send({ message: "Error activating poll" });
  }
};

exports.deletePoll = async (req, res) => {
  if (!req.userId) return res.status(401).send({ message: "Unauthorized" });
  const id = req.params.id;
  try {
    const data = await Poll.findByIdAndUpdate(id, { disabledAt: new Date() }, { new: true });
    if (!data) return res.status(404).send({ message: "Poll not found" });
    const log = new Log({ user: req.userId, action: "POLL_DELETED", details: `Poll ${id} disabled` });
    await log.save();
    res.send({ success: true, message: "Poll disabled successfully" });
  } catch (err) {
    res.status(500).send({ message: "Error disabling poll" });
  }
};

exports.getPollAudit = async (req, res) => {
  if (!req.userId) return res.status(401).send({ message: "Unauthorized" });
  const id = req.params.id;
  try {
    const totalVotes = await PollVote.countDocuments({ poll: id });
    const flaggedVotes = await PollVote.countDocuments({ poll: id, flagged: true });
    const bySubnet = await PollVote.aggregate([
      { $match: { poll: new mongoose.Types.ObjectId(id) } },
      { $group: { _id: "$ipSubnetHash", count: { $sum: 1 } } },
      { $sort: { count: -1 } },
      { $limit: 20 },
      ]);
    const byRegion = await PollVote.aggregate([
      { $match: { poll: new mongoose.Types.ObjectId(id) } },
      { $group: { _id: "$region", count: { $sum: 1 } } },
      { $sort: { count: -1 } },
      ]);
    res.send({ success: true, totalVotes, flaggedVotes, bySubnet, byRegion });
  } catch (err) {
    res.status(500).send({ message: "Error retrieving poll audit" });
  }
};

// ---- PUBLIC VOTE ENDPOINT (core anti-fraud logic) ----

exports.vote = async (req, res) => {
  const id = req.params.id;
  const { optionIndex, deviceToken } = req.body;

  if (optionIndex === undefined || optionIndex === null) {
    return res.status(400).send({ message: "optionIndex is required" });
  }
  if (!deviceToken || typeof deviceToken !== "string" || deviceToken.length < 8) {
    return res.status(400).send({ message: "A valid device token is required" });
  }

  try {
    const poll = await Poll.findOne({ _id: id, disabledAt: null });
    if (!poll) return res.status(404).send({ message: "Poll not found" });
    if (poll.status !== "active") {
      return res.status(409).send({ message: "This poll is not currently accepting votes" });
    }
    if (!poll.options[optionIndex]) {
      return res.status(400).send({ message: "Invalid option" });
    }

  const ip = getClientIp(req);
    const ua = req.headers["user-agent"] || "";
    const ipHash = hash(ip);
    const ipSubnetHash = hash(getSubnet(ip));
    const voterHash = hash(`${ip}|${ua}|${deviceToken}`);

  const already = await PollVote.findOne({ poll: id, voterHash });
    if (already) {
      return res.status(409).send({ message: "You have already voted in this poll" });
    }

  const maxPerIp = poll.settings?.maxVotesPerIpPerHour ?? 3;
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
    const recentFromIp = await PollVote.countDocuments({ poll: id, ipHash, createdAt: { $gte: oneHourAgo } });
    if (recentFromIp >= maxPerIp) {
      return res.status(429).send({ message: "Too many votes from this connection, please try again later" });
    }

  const subnetWindowMinutes = poll.isSensitive ? 10 : 30;
    const subnetThreshold = poll.isSensitive ? 15 : 40;
    const windowStart = new Date(Date.now() - subnetWindowMinutes * 60 * 1000);
    const recentFromSubnet = await PollVote.countDocuments({ poll: id, ipSubnetHash, createdAt: { $gte: windowStart } });
    let flagged = false;
    let flagReason = null;
    if (recentFromSubnet >= subnetThreshold) {
      flagged = true;
      flagReason = `Burst pattern: ${recentFromSubnet} votes from same network in ${subnetWindowMinutes}min`;
      if (!poll.flagged) {
        poll.flagged = true;
        poll.flagReason = flagReason;
      }
    }

  const { browser, os, deviceType } = parseUserAgent(ua);

  const voteDoc = new PollVote({
    poll: id,
    optionIndex,
    voterHash,
    ipHash,
    ipSubnetHash,
    region: req.headers["x-vercel-ip-city"] || req.headers["x-vercel-ip-country"] || null,
    userAgentSummary: { browser, os, deviceType },
    referrer: req.headers["referer"] || null,
    flagged,
    flagReason,
  });

  await voteDoc.save();

  poll.options[optionIndex].votes += 1;
    poll.totalVotes = (poll.totalVotes || 0) + 1;
    await poll.save();

  const revealResults = poll.settings?.showResultsAfterVote !== false;
    const result = poll.toObject();
    if (!revealResults) {
      result.options = result.options.map((o) => ({ _id: o._id, text: o.text }));
      result.totalVotes = undefined;
    }

  res.send({ success: true, poll: result });
  } catch (err) {
    if (err.code === 11000) {
      return res.status(409).send({ message: "You have already voted in this poll" });
    }
    res.status(500).send({ message: err.message || "Error registering vote" });
  }
};
