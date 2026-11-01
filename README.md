# AgeOverflow

An asynchronous web API for submitting analysis requests and retrieving generation-cohort results. Built for CSSE6400 Software Architecture at the University of Queensland, the project explores how to keep an API responsive while processing computationally expensive jobs in the background.

## What it does

- Accepts analysis requests and stores them in PostgreSQL.
- Queues jobs with Amazon SQS for background workers to process.
- Provides endpoints for request status, results, user history and customer statistics.
- Defines AWS infrastructure with separate scaling policies for API servers and workers.

## Technologies

Python, Flask, PostgreSQL, Docker, Terraform, and AWS services including EC2 Auto Scaling, RDS, SQS, S3, Application Load Balancer and CloudWatch.

## Project scope

This repository contains my Stage 3 API, worker and cloud infrastructure implementation. Analysis is performed by the supplied [AgeOverflow engine](https://github.com/CSSE6400/AgeOverflow-Engine), which simulates cohort analysis and processing load; it is not a real age-estimation model or an engine I developed.
