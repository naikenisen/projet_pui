# Anonymises the CSV files by replacing the NDA with random 9-digit identifiers.

BIO <- read.csv("~/coding/dataset_projet_pui/BIO.csv")
CLINIQUE <- read.csv("~/coding/dataset_projet_pui/CLINIQUE.csv")
TRAITEMENTS <- read.csv("~/coding/dataset_projet_pui/TRAITEMENTS.csv")

anonymise_tables <- function(dir = "~/coding/dataset_projet_pui",
                             tables = c("BIO", "CLINIQUE", "TRAITEMENTS"),
                             seed = NULL) {
  data <- lapply(tables, function(t) {
    read.csv(file.path(dir, paste0(t, ".csv")),
      colClasses = "character", check.names = FALSE,
      na.strings = character(0)
    )
  })
  names(data) <- tables

  all_nda <- unique(unlist(lapply(data, `[[`, "NDA")))
  if (!is.null(seed)) set.seed(seed)
  new_ids <- sample.int(9e8, length(all_nda)) + 99999999
  mapping <- setNames(as.character(new_ids), all_nda)

  for (t in tables) {
    df <- data[[t]]
    df$NDA <- unname(mapping[df$NDA])
    names(df)[names(df) == "NDA"] <- "numero_anonyme"
    write.csv(df, file.path(dir, paste0("ANONYMISED_", t, ".csv")),
      row.names = FALSE
    )
  }

  invisible(mapping)
}

anonymise_tables()
