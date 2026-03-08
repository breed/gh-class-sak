# project description

a swiss army knife for managing github classrooms

# language

- python to be deployed via pypi
- click for commandline parsing

# common flags

- for commands that change something `--dryrun` is needed to make the change, otherwise just print what would happen with a ⚠️ in front

# getting information about instructors and students

### listing student and instructor names, emails, and relationships

- find students and instructors of a section using this graphQL. instructors of a student share a courseSectionId with that student
    ```
    query MyQuery {
      course(id: "COURSEID") {
        name
        enrollmentsConnection {
          nodes {
            role {
              name
            }
            user {
              id
              name
              email
            }
            courseSectionId
          }
        }
      }
    }
    ```

### determine github information for students and instructors

find the github ids of all the students and instructors using the canvas REST API to get the profile for the given user id and look for the github link


# subcommands

- classrooms: list the classrooms and corresponding assignments
    - each assignment will have this format: CLASSROOM: ASSIGNMENT
- repos list: takes a CLASSROOM and ASSIGNMENT and lists each repo
    - line for each repo has this format: TEAM\tREPO\tMEMBER1,MEMBER2,...\tADMIN1,ADMIN2
    - if the `--alt` flag is give, any alternative repo names (previous names for the repo) will follow the admins with `\t#ALTREPO1,ALTREPO2`
- repos update: takes a file with the same format as `repos list` that will update the repo with the give members and admins
    - if any of the ids are emails, first resolve the email to the github id. print a noticeable error if the email does not resolve
