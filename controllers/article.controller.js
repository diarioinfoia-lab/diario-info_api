const Article = require("../models/article.model.js");
const Log = require("../models/log.model.js");
const User = require("../models/user.model.js");
const Category = require("../models/category.model.js");
const Interaction = require("../models/interaction.model.js");

// Helper to add interaction stats to articles
const addInteractionStats = async (articles, userId = null) => {
  if (!articles) return null;
  const isArray = Array.isArray(articles);
  const articleList = isArray ? articles : [articles];

  if (articleList.length === 0) return isArray ? [] : null;

  const articleIds = articleList.map((a) => a._id);
  const userIdStr = userId ? userId.toString() : null;
  const isIdValid = userIdStr && userIdStr.match(/^[0-9a-fA-F]{24}$/);

  const stats = await Interaction.aggregate([
    { $match: { article: { $in: articleIds } } },
    {
      $group: {
        _id: { article: "$article", type: "$interactionType" },
        count: { $sum: 1 },
      },
    },
  ]);

  // Get user-specific interactions if userId is provided
  const userInteractions = isIdValid
    ? await Interaction.find({
      user: userIdStr,
      article: { $in: articleIds },
    })
    : [];

  const results = articleList.map((article) => {
    const articleData = article.toJSON();
    const articleIdStr = article._id.toString();
    const articleStats = stats.filter(
      (s) => s._id.article.toString() === articleIdStr,
    );

    articleData.favoritesCount =
      articleStats.find((s) => s._id.type === "favorite")?.count || 0;
    articleData.savesCount =
      articleStats.find((s) => s._id.type === "save")?.count || 0;
    articleData.likesCount =
      articleStats.find((s) => s._id.type === "like")?.count || 0;

    // Add boolean flags for the current user
    if (isIdValid) {
      const userArticleInteractions = userInteractions.filter(
        (ui) => ui.article.toString() === articleIdStr,
      );
      articleData.isFavorite = userArticleInteractions.some(
        (ui) => ui.interactionType === "favorite",
      );
      articleData.isSaved = userArticleInteractions.some(
        (ui) => ui.interactionType === "save",
      );
      articleData.isLiked = userArticleInteractions.some(
        (ui) => ui.interactionType === "like",
      );
    } else {
      articleData.isFavorite = false;
      articleData.isSaved = false;
      articleData.isLiked = false;
    }

    return articleData;
  });

  return isArray ? results : results[0];
};

// Create and Save a new Article
exports.createArticle = async (req, res) => {
  // Validate request
  if (!req.userId) {
    return res
      .status(401)
      .send({ message: "Authentication required to create articles." });
  }

  if (!req.body) {
    return res.status(400).send({ message: "Content cannot be empty!" });
  }

  // Create an Article
  const article = new Article({
    title: req.body.title,
    slug: req.body.slug,
    description: req.body.description,
    content: req.body.content,
    imageId: req.body.imageId,
    category: req.body.category,
    status: req.body.status || "draft",
    isHighlighted: req.body.isHighlighted || false,
    author: req.body.author,
    date: req.body.date,
    location: req.body.location,
    publicationDate: req.body.publicationDate,
    commentsDisabled: req.body.commentsDisabled || false,
    embeddedVideoUrl: req.body.embeddedVideoUrl,
    keyPoints: req.body.keyPoints,
    priority: Number(req.body.priority) || 0,
    destination: req.body.destination,
    validityHours: req.body.validityHours,
    tags: req.body.tags,
    articleType: req.body.articleType,
    createdBy: req.userId,
  });

  // Save Article in the database
  try {
    const data = await article.save();

    // Log action
    if (req.userId) {
      const log = new Log({
        user: req.userId,
        action: "ARTICLE_CREATED",
        details: `Article ${data._id} created`,
      });
      await log.save();
    }
    res.status(201).send(data);
  } catch (err) {
    res.status(500).send({
      message: err.message || "Some error occurred while creating the Article.",
    });
  }
};

// Retrieve all Articles from the database.
exports.getArticles = async (req, res) => {
  if (!req.userId) {
    return res.status(401).send({ message: "Authentication required." });
  }

  // For admins or own user's articles
  const { title, status, category, destination, author } = req.query;
  const page = parseInt(req.query.page) || 1;
  const pageSize = parseInt(req.query.pageSize) || 10;
  const condition = {};

  if (title) {
    // We escape special characters to avoid errors in RegExp and ensure a literal search
    const escapedTitle = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const searchRegex = new RegExp(escapedTitle, "i");
    condition.$or = [
      { title: { $regex: searchRegex } },
      { description: { $regex: searchRegex } },
      { content: { $regex: searchRegex } },
    ];
  }

  if (status) {
    condition.status = status;
  }
  if (destination) {
    condition.destination = destination;
  }

  try {
    // Resolve category slug or ID to a valid Category ObjectId
    if (category) {
      const isObjectId = /^[0-9a-fA-F]{24}$/.test(category);
      const categoryDoc = await Category.findOne({
        [isObjectId ? "_id" : "slug"]: category,
        disabledAt: null,
      }).select("_id");

      if (!categoryDoc) {
        return res.send({
          success: true,
          articles: [],
          total: 0,
          totalPages: 0,
          nextPage: null,
        });
      }
      condition.category = categoryDoc._id;
    }

    // Validate userId format before DB query
    const userIdStr = req.userId ? req.userId.toString() : null;
    const isIdValid = userIdStr && userIdStr.match(/^[0-9a-fA-F]{24}$/);

    const requester = isIdValid ? await User.findById(userIdStr) : null;

    // If user is not an admin, they can only see their own articles.
    if (!requester || (!requester.isAdmin() && !requester.isDirector())) {
      condition.createdBy = req.userId;
    } else if (author) {
      // Admin can filter by author
      const users = await User.find({
        name: { $regex: new RegExp(author), $options: "i" },
      }).select("_id");
      condition.createdBy = { $in: users.map((u) => u._id) };
    }

    const total = await Article.countDocuments(condition);
    const totalPages = Math.ceil(total / pageSize);
    const nextPage = page + 1 <= totalPages ? page + 1 : null;

    let query = Article.find(condition)
      .sort({ createdAt: -1 })
      .skip((page - 1) * pageSize)
      .limit(pageSize);

    // Populate category data for all users
    query = query.populate("category", "name slug color");

    // Sort by createdAt descending (newest first)
    if (requester && requester.isAdmin()) {
      query = query.populate("createdBy", "name alias pictureUrl");
    }

    const articles = await query;

    const articlesWithStats = await addInteractionStats(articles, req.userId);

    res.send({
      success: true,
      articles: articlesWithStats,
      total,
      totalPages,
      nextPage,
    });
  } catch (err) {
    res.status(500).send({
      message: err.message || "Some error occurred while retrieving articles.",
    });
  }
};

// Retrieve all public Articles from the database.
exports.getPublicArticles = async (req, res) => {
  const { title, category, destination } = req.query;
  const page = parseInt(req.query.page) || 1;
  const pageSize = parseInt(req.query.pageSize) || 10;
  const condition = { status: "published" };
  const skip = req.query.skip !== undefined
    ? parseInt(req.query.skip)
    : (page - 1) * pageSize; // 👈 fallback a comportamiento actual


  if (title) {
    const escapedTitle = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    condition.$or = [
      { title: { $regex: escapedTitle, $options: "i" } },
      { description: { $regex: escapedTitle, $options: "i" } },
    ];
  }

  try {
    // Apply destination filter ONLY when no text search is active
    if (!title) {
      if (destination) {
        condition.destination = {
          $regex: `^${destination.trim()}$`,
          $options: "i",
        };
      } else {
        condition.$and = (condition.$and || []).concat([
          {
            $or: [
              { destination: { $exists: false } },
              { destination: null },
              { destination: "" },
              { destination: { $regex: "^general$", $options: "i" } },
            ],
          },
        ]);
      }
    }

    if (category) {
      const isObjectId = /^[0-9a-fA-F]{24}$/.test(category);
      const categoryDoc = await Category.findOne({
        [isObjectId ? "_id" : "slug"]: category,
        disabledAt: null,
      }).select("_id");

      if (!categoryDoc) {
        return res.send({
          success: true,
          articles: [],
          total: 0,
          totalPages: 0,
          nextPage: null,
        });
      }
      condition.category = categoryDoc._id;
    }

    const total = await Article.countDocuments(condition);
    const totalPages = Math.ceil(total / pageSize);
    const nextPage = page + 1 <= totalPages ? page + 1 : null;

    const sortedIds = await Article.aggregate([
      { $match: condition },
      {
        $addFields: {
          publicationDay: {
            $dateTrunc: {
              date: { $ifNull: ["$publicationDate", "$createdAt"] },
              unit: "day",
              timezone: "America/Argentina/Buenos_Aires",
            },
          },
        },
      },
      {
        $sort: {
          publicationDay: -1,
          priority: -1,
          publicationDate: -1,
          _id: -1,
        },
      },
      { $skip: skip },
      { $limit: pageSize },
      { $project: { _id: 1 } },
    ]);

    const orderedIds = sortedIds.map((a) => a._id);
    const articles = await Article.find({ _id: { $in: orderedIds } })
      .populate("createdBy", "name alias pictureUrl bio")
      .populate("category", "name slug color")
      .populate({
        path: "imageId",
        model: "File",
        select: "fileUrl thumbnailUrl originalName",
      });

    const articlesMap = new Map(articles.map((a) => [a._id.toString(), a]));
    const orderedArticles = orderedIds
      .map((id) => articlesMap.get(id.toString()))
      .filter(Boolean);

    const articlesWithStats = await addInteractionStats(
      orderedArticles,
      req.userId,
    );

    res.send({
      success: true,
      articles: articlesWithStats,
      total,
      totalPages,
      nextPage,
    });
  } catch (err) {
    console.error("💥 [getPublicArticles] Error:", err);
    res.status(500).send({
      message:
        err.message || "Some error occurred while retrieving public articles.",
    });
  }
};

// Find a single Article with an id
exports.getArticle = async (req, res) => {
  const id = req.params.id;

  try {
    let data;

    // If it looks like a valid ObjectId, try to find by ID first
    if (id.match(/^[0-9a-fA-F]{24}$/)) {
      data = await Article.findById(id)
        .populate("createdBy", "-password")
        .populate("category", "name slug color")
        .populate({
          path: "imageId",
          model: "File",
          select: "fileUrl thumbnailUrl originalName",
        });
    }

    // If not found (or not a valid ID), try to find by slug
    if (!data) {
      data = await Article.findOne({ slug: id })
        .populate("createdBy", "-password")
        .populate("category", "name slug color")
        .populate({
          path: "imageId",
          model: "File",
          select: "fileUrl thumbnailUrl originalName",
        });
    }

    if (!data)
      res.status(404).send({ message: "Not found Article with id " + id });
    else {
      const articleWithStats = await addInteractionStats(data, req.userId);
      res.send({
        success: true,
        article: articleWithStats,
      });
    }
  } catch (err) {
    res.status(500).send({ message: "Error retrieving Article with id=" + id });
  }
};

// Retrieve related Articles
exports.getRelatedArticles = async (req, res) => {
  const id = req.params.id;
  const limit = parseInt(req.query.limit) || 3;

  try {
    let article;

    // If it looks like a valid ObjectId, try to find by ID first
    if (id.match(/^[0-9a-fA-F]{24}$/)) {
      article = await Article.findById(id);
    }

    // If not found (or not a valid ID), try to find by slug
    if (!article) {
      article = await Article.findOne({ slug: id });
    }

    if (!article) {
      return res.status(404).send({ message: "Article not found" });
    }

    const articles = await Article.find({
      category: article.category,
      status: "published",
      _id: { $ne: article._id },
    })
      .sort({ publicationDate: -1 })
      .limit(limit)
      .populate("category", "name slug color")
      .populate("author", "name alias pictureUrl")
      .populate("createdBy", "name alias pictureUrl bio")
      .populate({
        path: "imageId",
        model: "File",
        select: "fileUrl thumbnailUrl originalName",
      });

    const articlesWithStats = await addInteractionStats(articles, req.userId);

    res.send({ success: true, articles: articlesWithStats });
  } catch (err) {
    res.status(500).send({ message: "Error retrieving related articles" });
  }
};

// Update an Article by the id in the request
exports.updateArticle = async (req, res) => {
  if (!req.userId) {
    return res.status(401).send({ message: "Authentication required." });
  }

  if (!req.body) {
    return res.status(400).send({
      message: "Data to update can not be empty!",
    });
  }

  const id = req.params.id;

  try {
    const data = await Article.findByIdAndUpdate(id, req.body, {
      useFindAndModify: false,
      new: true, // Returns the modified document
    });
    if (!data) {
      res.status(404).send({
        message: `Cannot update Article with id=${id}. Maybe Article was not found!`,
      });
    } else {
      // Log action
      if (req.userId) {
        const log = new Log({
          user: req.userId,
          action: "ARTICLE_UPDATED",
          details: `Article ${id} updated`,
        });
        await log.save();
      }
      res.send(data);
    }
  } catch (err) {
    res.status(500).send({
      message: "Error updating Article with id=" + id,
    });
  }
};

// Delete an Article with the specified id in the request
exports.deleteArticle = async (req, res) => {
  const id = req.params.id;

  if (!req.userId) {
    return res.status(401).send({ message: "Authentication required." });
  }

  try {
    const data = await Article.findByIdAndDelete(id);
    if (!data) {
      res.status(404).send({
        message: `Cannot delete Article with id=${id}. Maybe Article was not found!`,
      });
    } else {
      // Log action
      if (req.userId) {
        const log = new Log({
          user: req.userId,
          action: "ARTICLE_DELETED",
          details: `Article ${id} deleted`,
        });
        await log.save();
      }
      res.send({
        message: "Article was deleted successfully!",
      });
    }
  } catch (err) {
    res.status(500).send({
      message: "Could not delete Article with id=" + id,
    });
  }
};

// Retrieve article rankings based on favorites (votes) and saves
exports.getArticleRankings = async (req, res) => {
  // Ensure limit is a valid number, default to 10
  const limit = Math.max(1, parseInt(req.query.limit) || 10);

  try {
    const getRankingByType = async (type) => {
      // 1. Get IDs of top articles based on interaction counts from the general public
      const topInteractedStats = await Interaction.aggregate([
        {
          $match: {
            interactionType: type,
            article: { $ne: null },
          },
        },
        {
          $group: {
            _id: "$article",
            interactionCount: { $sum: 1 },
          },
        },
        { $sort: { interactionCount: -1 } },
        { $limit: limit },
      ]);

      const rankedArticleIds = topInteractedStats.map((s) => s._id);

      // 2. Fetch the articles that have these interactions (only if they are published)
      let articles = [];
      if (rankedArticleIds.length > 0) {
        articles = await Article.find({
          _id: { $in: rankedArticleIds },
          status: "published",
        })
          .populate("author", "name alias pictureUrl")
          .populate("createdBy", "name alias pictureUrl bio")
          .populate("category", "name slug color")
          .populate({
            path: "imageId",
            model: "File",
            select: "fileUrl thumbnailUrl originalName",
          });
      }

      // 3. FILLER: If articles count is less than limit, fill with newest published ones
      if (articles.length < limit) {
        const alreadyIncludedIds = articles.map((a) => a._id);
        const fillerArticles = await Article.find({
          status: "published",
          _id: { $nin: alreadyIncludedIds },
        })
          .sort({ publicationDate: -1, createdAt: -1 })
          .limit(limit - articles.length)
          .populate("author", "name alias pictureUrl")
          .populate("createdBy", "name alias pictureUrl bio")
          .populate("category", "name slug color")
          .populate({
            path: "imageId",
            model: "File",
            select: "fileUrl thumbnailUrl originalName",
          });

        articles = [...articles, ...fillerArticles];
      }

      // 4. Enrich with global interaction stats (counts) for all articles in the list
      const articlesWithStats = await addInteractionStats(articles, null);

      // 5. Final Sorting: By interaction count (desc) then by Date (desc)
      const countField = type === "favorite" ? "favoritesCount" : "savesCount";

      return articlesWithStats
        .sort((a, b) => {
          const countA = a[countField] || 0;
          const countB = b[countField] || 0;
          if (countB !== countA) return countB - countA;

          const timeA = new Date(
            a.publicationDate || a.createdAt || 0,
          ).getTime();
          const timeB = new Date(
            b.publicationDate || b.createdAt || 0,
          ).getTime();
          return timeB - timeA;
        })
        .slice(0, limit);
    };

    // Execute both aggregations in parallel for maximum performance
    const [mostFavorited, mostSaved] = await Promise.all([
      getRankingByType("favorite"),
      getRankingByType("save"),
    ]);

    res.status(200).json({
      success: true,
      rankings: {
        mostFavorited,
        mostSaved,
      },
    });
  } catch (err) {
    console.log("[Error retrieving article rankings]:", err);

    res.status(500).send({
      message:
        err.message || "Some error occurred while retrieving article rankings.",
    });
  }
};
